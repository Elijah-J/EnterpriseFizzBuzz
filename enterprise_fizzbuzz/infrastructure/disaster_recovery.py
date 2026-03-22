"""
Enterprise FizzBuzz Platform - Disaster Recovery & Backup/Restore Module

Implements a comprehensive disaster recovery framework with Write-Ahead
Logging (WAL), snapshot-based backups, Point-in-Time Recovery (PITR),
retention policies, DR drills, and an ASCII recovery dashboard.

All backups, WAL entries, and snapshots are stored exclusively in RAM,
which means they are protected against everything EXCEPT the one thing
that actually destroys data: process termination. This is the disaster
recovery equivalent of storing your fire extinguisher inside the building
it's supposed to protect, but with SHA-256 checksums.

The retention policy maintains 24 hourly, 7 daily, 4 weekly, and 12
monthly backups for a process that runs for less than one second. The
mathematical impossibility of this schedule is not a bug; it is a
feature that ensures the retention manager always has work to do.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    BackupNotFoundError,
    BackupVaultFullError,
    DisasterRecoveryError,
    DRDashboardRenderError,
    DRDrillError,
    PITRError,
    RetentionPolicyError,
    RPOViolationError,
    RTOViolationError,
    SnapshotCreationError,
    SnapshotRestorationError,
    WALCorruptionError,
    WALReplayError,
)
from enterprise_fizzbuzz.domain.models import Event, EventType, ProcessingContext
from enterprise_fizzbuzz.domain.interfaces import IMiddleware

logger = logging.getLogger(__name__)


# ================================================================
# Write-Ahead Log (WAL)
# ================================================================
# A SHA-256 checksummed, append-only, in-memory log that tracks
# every dict mutation in the FizzBuzz processing pipeline. In a
# real database, the WAL would be written to durable storage
# before the actual mutation occurs. Here, we write it to the
# same RAM that the mutation happens in, achieving zero additional
# durability while adding significant computational overhead.
# This is enterprise engineering at its finest.
# ================================================================


@dataclass(frozen=True)
class WALEntry:
    """A single entry in the Write-Ahead Log.

    Each entry records a dict mutation with a SHA-256 checksum
    to detect tampering. Since the WAL and the data it protects
    both live in RAM, the only entity that could tamper with it
    is the process itself, but paranoia is a virtue in enterprise
    disaster recovery.

    Attributes:
        sequence: Monotonically increasing sequence number.
        timestamp: When the mutation occurred (UTC).
        operation: The type of mutation (e.g., "SET", "DELETE", "CLEAR").
        key: The dict key that was mutated.
        value: The new value (serialized to JSON for checksumming).
        checksum: SHA-256 hash of the entry contents.
        entry_id: Unique identifier for this WAL entry.
    """

    sequence: int
    timestamp: datetime
    operation: str
    key: str
    value: Any
    checksum: str
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def verify(self) -> bool:
        """Verify the integrity of this WAL entry via checksum."""
        computed = _compute_wal_checksum(
            self.sequence, self.timestamp, self.operation, self.key, self.value
        )
        return computed == self.checksum


def _compute_wal_checksum(
    sequence: int,
    timestamp: datetime,
    operation: str,
    key: str,
    value: Any,
) -> str:
    """Compute SHA-256 checksum for a WAL entry.

    The checksum covers the sequence number, timestamp, operation,
    key, and serialized value. This ensures that any modification
    to any field will be detected, even though the only thing that
    could modify it is us. Trust no one, not even yourself.
    """
    payload = f"{sequence}|{timestamp.isoformat()}|{operation}|{key}|{json.dumps(value, sort_keys=True, default=str)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class WriteAheadLog:
    """In-memory Write-Ahead Log with SHA-256 checksummed entries.

    Provides append-only logging of dict mutations with integrity
    verification. The log is stored in a Python list, which means
    it is exactly as durable as a variable assignment — i.e., not
    at all. But every entry has a cryptographic checksum, so at
    least we'll know if our ephemeral data has been tampered with
    before it vanishes forever.
    """

    def __init__(
        self,
        max_entries: int = 10000,
        verify_on_read: bool = True,
        event_bus: Any = None,
    ) -> None:
        self._entries: list[WALEntry] = []
        self._sequence_counter: int = 0
        self._max_entries = max_entries
        self._verify_on_read = verify_on_read
        self._event_bus = event_bus
        self._corruption_count: int = 0

    def append(self, operation: str, key: str, value: Any) -> WALEntry:
        """Append a new entry to the WAL.

        Args:
            operation: The mutation type (SET, DELETE, CLEAR).
            key: The dict key being mutated.
            value: The new value for the key.

        Returns:
            The created WALEntry with its checksum.

        Raises:
            DisasterRecoveryError: If the WAL has exceeded max_entries.
        """
        if len(self._entries) >= self._max_entries:
            # Rotate: discard oldest half (enterprise log rotation)
            half = self._max_entries // 2
            self._entries = self._entries[half:]
            logger.info(
                "WAL rotated: discarded %d oldest entries. "
                "The Write-Ahead Log has performed its own garbage collection, "
                "which is exactly as reliable as it sounds.",
                half,
            )

        self._sequence_counter += 1
        timestamp = datetime.now(timezone.utc)
        checksum = _compute_wal_checksum(
            self._sequence_counter, timestamp, operation, key, value
        )

        entry = WALEntry(
            sequence=self._sequence_counter,
            timestamp=timestamp,
            operation=operation,
            key=key,
            value=value,
            checksum=checksum,
        )
        self._entries.append(entry)

        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.DR_WAL_ENTRY_APPENDED,
                payload={
                    "sequence": entry.sequence,
                    "operation": operation,
                    "key": key,
                },
                source="WriteAheadLog",
            ))

        return entry

    def get_entries(
        self,
        since_sequence: int = 0,
        until_time: Optional[datetime] = None,
    ) -> list[WALEntry]:
        """Retrieve WAL entries, optionally filtered by sequence or time.

        Args:
            since_sequence: Only return entries after this sequence number.
            until_time: Only return entries before this timestamp.

        Returns:
            List of WALEntry objects matching the criteria.
        """
        result = []
        for entry in self._entries:
            if entry.sequence <= since_sequence:
                continue
            if until_time is not None and entry.timestamp > until_time:
                break

            if self._verify_on_read and not entry.verify():
                self._corruption_count += 1
                if self._event_bus is not None:
                    self._event_bus.publish(Event(
                        event_type=EventType.DR_WAL_CHECKSUM_FAILED,
                        payload={"sequence": entry.sequence},
                        source="WriteAheadLog",
                    ))
                raise WALCorruptionError(
                    entry.sequence,
                    entry.checksum,
                    _compute_wal_checksum(
                        entry.sequence, entry.timestamp,
                        entry.operation, entry.key, entry.value,
                    ),
                )

            if self._event_bus is not None:
                self._event_bus.publish(Event(
                    event_type=EventType.DR_WAL_CHECKSUM_VERIFIED,
                    payload={"sequence": entry.sequence},
                    source="WriteAheadLog",
                ))

            result.append(entry)

        return result

    def replay(
        self,
        state: dict[str, Any],
        since_sequence: int = 0,
        until_time: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Replay WAL entries onto a state dict to reconstruct it.

        This is the heart of Write-Ahead Logging: by replaying
        every mutation in order, we can reconstruct the exact state
        at any point in time. The fact that the state we're
        reconstructing also lives in RAM and could have been
        preserved simply by not deleting it is beside the point.

        Args:
            state: The base state dict to replay onto (will be mutated).
            since_sequence: Start replaying from this sequence number.
            until_time: Stop replaying at this timestamp.

        Returns:
            The mutated state dict.
        """
        entries = self.get_entries(since_sequence=since_sequence, until_time=until_time)

        for entry in entries:
            try:
                if entry.operation == "SET":
                    state[entry.key] = copy.deepcopy(entry.value)
                elif entry.operation == "DELETE":
                    state.pop(entry.key, None)
                elif entry.operation == "CLEAR":
                    state.clear()
                else:
                    raise WALReplayError(
                        entry.sequence,
                        f"Unknown operation: {entry.operation}",
                    )
            except (WALReplayError, WALCorruptionError):
                raise
            except Exception as e:
                raise WALReplayError(entry.sequence, str(e)) from e

        return state

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @property
    def latest_sequence(self) -> int:
        return self._sequence_counter

    @property
    def corruption_count(self) -> int:
        return self._corruption_count

    def get_statistics(self) -> dict[str, Any]:
        """Return WAL statistics for the dashboard."""
        ops: dict[str, int] = {}
        for e in self._entries:
            ops[e.operation] = ops.get(e.operation, 0) + 1

        return {
            "total_entries": len(self._entries),
            "latest_sequence": self._sequence_counter,
            "max_entries": self._max_entries,
            "corruption_count": self._corruption_count,
            "operations": ops,
            "first_timestamp": self._entries[0].timestamp.isoformat() if self._entries else None,
            "last_timestamp": self._entries[-1].timestamp.isoformat() if self._entries else None,
            "storage_location": "RAM (volatile)",
            "durability_guarantee": "None whatsoever",
        }


# ================================================================
# Snapshot Engine
# ================================================================
# The snapshot engine serializes the entire application state into
# a point-in-time checkpoint. In a real database, this would be
# written to disk, tape, or a remote storage service. Here, it's
# copied to a different Python dict in the same RAM. The deep copy
# provides protection against accidental mutation but absolutely
# no protection against the process exiting, which is the only
# scenario where you'd actually need a backup.
# ================================================================


@dataclass(frozen=True)
class SnapshotManifest:
    """Metadata about a snapshot — the label on the backup tape.

    Attributes:
        snapshot_id: Unique identifier for this snapshot.
        created_at: When the snapshot was taken (UTC).
        wal_sequence: The WAL sequence number at snapshot time.
        state_hash: SHA-256 hash of the serialized state.
        entry_count: Number of entries in the snapshotted state.
        size_bytes: Approximate size of the serialized state.
        description: Human-readable description of the snapshot.
    """

    snapshot_id: str
    created_at: datetime
    wal_sequence: int
    state_hash: str
    entry_count: int
    size_bytes: int
    description: str = ""


@dataclass
class Snapshot:
    """A point-in-time snapshot of application state.

    Contains both the manifest (metadata) and the actual state
    data. The state is deep-copied to prevent accidental mutation,
    because in enterprise software, defensive copying is not
    paranoia — it's standard operating procedure.

    Attributes:
        manifest: Snapshot metadata and integrity information.
        state: Deep copy of the application state at snapshot time.
    """

    manifest: SnapshotManifest
    state: dict[str, Any]


class SnapshotEngine:
    """Creates and restores point-in-time state snapshots.

    The snapshot engine is the backbone of the backup system. It
    takes a Python dict, deep-copies it, computes a SHA-256 hash
    of the serialized contents, and stores it in another Python
    dict. This provides cryptographic integrity verification of
    data that will be lost the moment the process terminates.
    """

    def __init__(self, event_bus: Any = None) -> None:
        self._event_bus = event_bus
        self._snapshot_count: int = 0

    def create_snapshot(
        self,
        state: dict[str, Any],
        wal_sequence: int = 0,
        description: str = "",
    ) -> Snapshot:
        """Create a snapshot of the given state.

        Args:
            state: The dict to snapshot.
            wal_sequence: The current WAL sequence for PITR correlation.
            description: Human-readable description.

        Returns:
            A Snapshot containing the deep-copied state and manifest.
        """
        try:
            state_copy = copy.deepcopy(state)
            serialized = json.dumps(state_copy, sort_keys=True, default=str)
            state_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
            size_bytes = len(serialized.encode("utf-8"))

            self._snapshot_count += 1
            snapshot_id = f"snap-{self._snapshot_count:04d}-{uuid.uuid4().hex[:8]}"

            manifest = SnapshotManifest(
                snapshot_id=snapshot_id,
                created_at=datetime.now(timezone.utc),
                wal_sequence=wal_sequence,
                state_hash=state_hash,
                entry_count=len(state_copy),
                size_bytes=size_bytes,
                description=description or f"Auto-snapshot #{self._snapshot_count}",
            )

            snapshot = Snapshot(manifest=manifest, state=state_copy)

            if self._event_bus is not None:
                self._event_bus.publish(Event(
                    event_type=EventType.DR_SNAPSHOT_CREATED,
                    payload={
                        "snapshot_id": snapshot_id,
                        "wal_sequence": wal_sequence,
                        "entry_count": len(state_copy),
                        "size_bytes": size_bytes,
                    },
                    source="SnapshotEngine",
                ))

            return snapshot

        except Exception as e:
            raise SnapshotCreationError(str(e)) from e

    def restore_snapshot(self, snapshot: Snapshot) -> dict[str, Any]:
        """Restore state from a snapshot.

        Verifies the snapshot integrity via SHA-256 hash before
        returning a deep copy of the stored state. Because even
        though the snapshot has been sitting in RAM for microseconds,
        we must verify it hasn't been tampered with.

        Args:
            snapshot: The snapshot to restore.

        Returns:
            A deep copy of the snapshot's state.
        """
        try:
            state_copy = copy.deepcopy(snapshot.state)

            # Verify integrity
            serialized = json.dumps(state_copy, sort_keys=True, default=str)
            current_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

            if current_hash != snapshot.manifest.state_hash:
                if self._event_bus is not None:
                    self._event_bus.publish(Event(
                        event_type=EventType.DR_SNAPSHOT_CORRUPTED,
                        payload={"snapshot_id": snapshot.manifest.snapshot_id},
                        source="SnapshotEngine",
                    ))
                raise SnapshotRestorationError(
                    snapshot.manifest.snapshot_id,
                    f"Hash mismatch: expected {snapshot.manifest.state_hash[:16]}..., "
                    f"got {current_hash[:16]}...",
                )

            if self._event_bus is not None:
                self._event_bus.publish(Event(
                    event_type=EventType.DR_SNAPSHOT_RESTORED,
                    payload={
                        "snapshot_id": snapshot.manifest.snapshot_id,
                        "entry_count": len(state_copy),
                    },
                    source="SnapshotEngine",
                ))

            return state_copy

        except SnapshotRestorationError:
            raise
        except Exception as e:
            raise SnapshotRestorationError(
                snapshot.manifest.snapshot_id, str(e)
            ) from e

    @property
    def total_snapshots_created(self) -> int:
        return self._snapshot_count


# ================================================================
# Backup Manager
# ================================================================
# The backup manager maintains a vault of snapshots with a maximum
# capacity. When the vault is full, the oldest backup is evicted
# to make room, because in enterprise disaster recovery, even your
# safety nets have limits. The vault is stored in RAM, so "maximum
# capacity" really means "however much memory Python can allocate
# before the OS starts killing processes."
# ================================================================


class BackupManager:
    """Manages a vault of state snapshots with capacity limits.

    Provides CRUD operations on backups with automatic eviction
    of the oldest backup when capacity is exceeded. All backups
    are stored in a Python list in RAM, which provides the same
    level of durability as writing them on a whiteboard — except
    without the advantage of being visible from across the room.
    """

    def __init__(
        self,
        max_snapshots: int = 50,
        snapshot_engine: Optional[SnapshotEngine] = None,
        event_bus: Any = None,
    ) -> None:
        self._vault: list[Snapshot] = []
        self._max_snapshots = max_snapshots
        self._snapshot_engine = snapshot_engine or SnapshotEngine(event_bus=event_bus)
        self._event_bus = event_bus
        self._total_backups_created: int = 0
        self._total_backups_deleted: int = 0

    def create_backup(
        self,
        state: dict[str, Any],
        wal_sequence: int = 0,
        description: str = "",
    ) -> Snapshot:
        """Create a new backup and add it to the vault.

        If the vault is at capacity, the oldest backup is evicted
        first. This is the backup equivalent of FIFO eviction:
        first backed up, first forgotten.

        Args:
            state: The state dict to back up.
            wal_sequence: Current WAL sequence for PITR correlation.
            description: Human-readable backup description.

        Returns:
            The created Snapshot.
        """
        # Evict oldest if at capacity
        if len(self._vault) >= self._max_snapshots:
            evicted = self._vault.pop(0)
            self._total_backups_deleted += 1
            if self._event_bus is not None:
                self._event_bus.publish(Event(
                    event_type=EventType.DR_BACKUP_DELETED,
                    payload={
                        "snapshot_id": evicted.manifest.snapshot_id,
                        "reason": "vault_capacity_exceeded",
                    },
                    source="BackupManager",
                ))
            logger.info(
                "Backup vault full (%d/%d). Evicted oldest backup: %s. "
                "The backup that was supposed to protect your data has been "
                "sacrificed to make room for newer backups.",
                self._max_snapshots, self._max_snapshots,
                evicted.manifest.snapshot_id,
            )

        snapshot = self._snapshot_engine.create_snapshot(
            state, wal_sequence, description
        )
        self._vault.append(snapshot)
        self._total_backups_created += 1

        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.DR_BACKUP_CREATED,
                payload={
                    "snapshot_id": snapshot.manifest.snapshot_id,
                    "vault_size": len(self._vault),
                    "max_capacity": self._max_snapshots,
                },
                source="BackupManager",
            ))

        return snapshot

    def get_backup(self, snapshot_id: str) -> Snapshot:
        """Retrieve a backup by its snapshot ID.

        Args:
            snapshot_id: The unique identifier of the backup.

        Returns:
            The requested Snapshot.

        Raises:
            BackupNotFoundError: If no backup with the given ID exists.
        """
        for snap in self._vault:
            if snap.manifest.snapshot_id == snapshot_id:
                return snap
        raise BackupNotFoundError(snapshot_id)

    def get_latest_backup(self) -> Optional[Snapshot]:
        """Return the most recent backup, or None if the vault is empty."""
        return self._vault[-1] if self._vault else None

    def get_backup_before(self, target_time: datetime) -> Optional[Snapshot]:
        """Return the most recent backup created before the target time."""
        candidates = [
            s for s in self._vault
            if s.manifest.created_at <= target_time
        ]
        return candidates[-1] if candidates else None

    def list_backups(self) -> list[SnapshotManifest]:
        """Return manifests for all backups in the vault."""
        return [s.manifest for s in self._vault]

    def delete_backup(self, snapshot_id: str) -> None:
        """Delete a backup from the vault.

        Args:
            snapshot_id: The unique identifier of the backup to delete.

        Raises:
            BackupNotFoundError: If no backup with the given ID exists.
        """
        for i, snap in enumerate(self._vault):
            if snap.manifest.snapshot_id == snapshot_id:
                self._vault.pop(i)
                self._total_backups_deleted += 1
                if self._event_bus is not None:
                    self._event_bus.publish(Event(
                        event_type=EventType.DR_BACKUP_DELETED,
                        payload={
                            "snapshot_id": snapshot_id,
                            "reason": "manual_deletion",
                        },
                        source="BackupManager",
                    ))
                return
        raise BackupNotFoundError(snapshot_id)

    @property
    def vault_size(self) -> int:
        return len(self._vault)

    @property
    def vault_capacity(self) -> int:
        return self._max_snapshots

    def get_statistics(self) -> dict[str, Any]:
        """Return backup vault statistics."""
        total_size = sum(s.manifest.size_bytes for s in self._vault)
        return {
            "vault_size": len(self._vault),
            "max_capacity": self._max_snapshots,
            "utilization_pct": (len(self._vault) / self._max_snapshots * 100)
            if self._max_snapshots > 0 else 0,
            "total_size_bytes": total_size,
            "total_backups_created": self._total_backups_created,
            "total_backups_deleted": self._total_backups_deleted,
            "oldest_backup": self._vault[0].manifest.created_at.isoformat()
            if self._vault else None,
            "newest_backup": self._vault[-1].manifest.created_at.isoformat()
            if self._vault else None,
            "storage_medium": "RAM (volatile, ephemeral, fleeting)",
        }


# ================================================================
# Point-in-Time Recovery (PITR) Engine
# ================================================================
# PITR combines a base snapshot with WAL replay to reconstruct
# state at any arbitrary moment in time. In a production database,
# this enables recovery to the exact second before a catastrophic
# failure. Here, it enables recovery to the exact microsecond
# before the Python process exited, which is impressive but
# ultimately pointless because the recovery itself happens in
# a new process that has no memory of the old one.
# ================================================================


class PITREngine:
    """Point-in-Time Recovery engine.

    Combines base snapshots with WAL replay to reconstruct state
    at any arbitrary timestamp. This is the crown jewel of the
    disaster recovery subsystem: the ability to travel back in
    time to any moment during the process's sub-second lifetime.

    The PITR engine works by:
    1. Finding the most recent snapshot before the target time
    2. Restoring that snapshot's state
    3. Replaying WAL entries from the snapshot's sequence to the target time
    4. Returning the reconstructed state

    This three-step process adds significant latency to achieve
    something that could have been done by simply keeping the
    original dict around, but that would not be enterprise-grade.
    """

    def __init__(
        self,
        wal: WriteAheadLog,
        backup_manager: BackupManager,
        snapshot_engine: SnapshotEngine,
        event_bus: Any = None,
    ) -> None:
        self._wal = wal
        self._backup_manager = backup_manager
        self._snapshot_engine = snapshot_engine
        self._event_bus = event_bus
        self._recovery_count: int = 0
        self._total_recovery_time_us: float = 0

    def recover_to_time(self, target_time: datetime) -> dict[str, Any]:
        """Recover state to a specific point in time.

        Args:
            target_time: The target timestamp for recovery.

        Returns:
            The reconstructed state dict at the target time.

        Raises:
            PITRError: If recovery fails for any reason.
        """
        start_us = time.perf_counter() * 1_000_000

        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.DR_PITR_STARTED,
                payload={"target_time": target_time.isoformat()},
                source="PITREngine",
            ))

        try:
            # Step 1: Find the base snapshot
            base_snapshot = self._backup_manager.get_backup_before(target_time)

            if base_snapshot is None:
                # No snapshot available, start from empty state
                base_state: dict[str, Any] = {}
                base_sequence = 0
            else:
                base_state = self._snapshot_engine.restore_snapshot(base_snapshot)
                base_sequence = base_snapshot.manifest.wal_sequence

            # Step 2: Replay WAL entries from snapshot to target time
            recovered_state = self._wal.replay(
                base_state,
                since_sequence=base_sequence,
                until_time=target_time,
            )

            elapsed_us = time.perf_counter() * 1_000_000 - start_us
            self._recovery_count += 1
            self._total_recovery_time_us += elapsed_us

            if self._event_bus is not None:
                self._event_bus.publish(Event(
                    event_type=EventType.DR_PITR_COMPLETED,
                    payload={
                        "target_time": target_time.isoformat(),
                        "recovery_time_us": elapsed_us,
                        "wal_entries_replayed": len(
                            self._wal.get_entries(
                                since_sequence=base_sequence,
                                until_time=target_time,
                            )
                        ),
                        "base_snapshot": base_snapshot.manifest.snapshot_id
                        if base_snapshot else "empty_state",
                    },
                    source="PITREngine",
                ))

            return recovered_state

        except (PITRError, WALCorruptionError, WALReplayError,
                SnapshotRestorationError):
            raise
        except Exception as e:
            if self._event_bus is not None:
                self._event_bus.publish(Event(
                    event_type=EventType.DR_PITR_FAILED,
                    payload={
                        "target_time": target_time.isoformat(),
                        "error": str(e),
                    },
                    source="PITREngine",
                ))
            raise PITRError(target_time.isoformat(), str(e)) from e

    def recover_to_latest(self) -> dict[str, Any]:
        """Recover to the most recent available state."""
        return self.recover_to_time(datetime.now(timezone.utc))

    @property
    def recovery_count(self) -> int:
        return self._recovery_count

    @property
    def average_recovery_time_us(self) -> float:
        if self._recovery_count == 0:
            return 0.0
        return self._total_recovery_time_us / self._recovery_count

    def get_statistics(self) -> dict[str, Any]:
        return {
            "total_recoveries": self._recovery_count,
            "total_recovery_time_us": self._total_recovery_time_us,
            "average_recovery_time_us": self.average_recovery_time_us,
        }


# ================================================================
# Retention Policy & Manager
# ================================================================
# The retention policy maintains 24 hourly, 7 daily, 4 weekly,
# and 12 monthly backups. For a process that runs for less than
# one second, this retention schedule is aspirational to the point
# of absurdity. The retention manager dutifully categorizes each
# backup into its retention tier and prunes the excess, even though
# every backup was created within the same second and there are
# no "hourly" or "daily" boundaries to speak of.
# ================================================================


@dataclass(frozen=True)
class RetentionPolicy:
    """Defines backup retention tiers.

    Attributes:
        hourly: Maximum hourly backups to retain.
        daily: Maximum daily backups to retain.
        weekly: Maximum weekly backups to retain.
        monthly: Maximum monthly backups to retain.
    """

    hourly: int = 24
    daily: int = 7
    weekly: int = 4
    monthly: int = 12

    @property
    def total_slots(self) -> int:
        return self.hourly + self.daily + self.weekly + self.monthly


class RetentionManager:
    """Applies retention policies to the backup vault.

    The retention manager categorizes backups into hourly, daily,
    weekly, and monthly tiers based on their creation timestamps.
    For a process that runs for 0.8 seconds, ALL backups fall into
    the "sub-second" tier, which is not a real retention tier but
    accurately describes the situation. The manager valiantly
    pretends that time-based retention makes sense anyway.
    """

    def __init__(
        self,
        policy: RetentionPolicy,
        event_bus: Any = None,
    ) -> None:
        self._policy = policy
        self._event_bus = event_bus
        self._pruned_count: int = 0

    def apply(self, backups: list[Snapshot]) -> list[Snapshot]:
        """Apply the retention policy, returning backups to keep.

        Since all backups were created within the same second,
        this function essentially just keeps the N most recent
        backups where N is the total retention slots. But it
        goes through the ceremony of categorizing them into
        hourly/daily/weekly/monthly tiers first, because
        enterprise compliance demands the paperwork.

        Args:
            backups: List of all backups to evaluate.

        Returns:
            List of backups that survive the retention policy.
        """
        if not backups:
            return []

        now = datetime.now(timezone.utc)

        # Categorize backups into retention tiers
        hourly: list[Snapshot] = []
        daily: list[Snapshot] = []
        weekly: list[Snapshot] = []
        monthly: list[Snapshot] = []

        for backup in sorted(backups, key=lambda b: b.manifest.created_at, reverse=True):
            age = now - backup.manifest.created_at
            if age < timedelta(hours=1):
                hourly.append(backup)
            elif age < timedelta(days=1):
                daily.append(backup)
            elif age < timedelta(weeks=1):
                weekly.append(backup)
            else:
                monthly.append(backup)

        # If all backups are within the same second (which they always are),
        # they all go into 'hourly'. This is working as intended.
        if not hourly and not daily and not weekly and not monthly:
            # All backups have somehow been categorized into the void.
            # Keep them all in hourly as a safety measure.
            hourly = list(backups)

        # Apply retention limits per tier
        kept_hourly = hourly[: self._policy.hourly]
        kept_daily = daily[: self._policy.daily]
        kept_weekly = weekly[: self._policy.weekly]
        kept_monthly = monthly[: self._policy.monthly]

        kept = set()
        for snap in kept_hourly + kept_daily + kept_weekly + kept_monthly:
            kept.add(snap.manifest.snapshot_id)

        pruned = [b for b in backups if b.manifest.snapshot_id not in kept]
        self._pruned_count += len(pruned)

        if self._event_bus is not None and pruned:
            self._event_bus.publish(Event(
                event_type=EventType.DR_RETENTION_POLICY_APPLIED,
                payload={
                    "total_backups": len(backups),
                    "retained": len(kept),
                    "pruned": len(pruned),
                    "tiers": {
                        "hourly": len(kept_hourly),
                        "daily": len(kept_daily),
                        "weekly": len(kept_weekly),
                        "monthly": len(kept_monthly),
                    },
                },
                source="RetentionManager",
            ))

        return [b for b in backups if b.manifest.snapshot_id in kept]

    def get_retention_summary(self, backups: list[Snapshot]) -> dict[str, Any]:
        """Return a summary of how backups map to retention tiers."""
        now = datetime.now(timezone.utc)

        tiers: dict[str, int] = {"hourly": 0, "daily": 0, "weekly": 0, "monthly": 0}
        for backup in backups:
            age = now - backup.manifest.created_at
            if age < timedelta(hours=1):
                tiers["hourly"] += 1
            elif age < timedelta(days=1):
                tiers["daily"] += 1
            elif age < timedelta(weeks=1):
                tiers["weekly"] += 1
            else:
                tiers["monthly"] += 1

        return {
            "policy": {
                "hourly": self._policy.hourly,
                "daily": self._policy.daily,
                "weekly": self._policy.weekly,
                "monthly": self._policy.monthly,
                "total_slots": self._policy.total_slots,
            },
            "current": tiers,
            "total_pruned": self._pruned_count,
            "compliance": "IMPOSSIBLE (process runs for <1 second)",
        }


# ================================================================
# DR Drill Runner
# ================================================================
# The DR drill intentionally destroys state, then attempts to
# recover it using the backup and PITR systems. It measures the
# actual Recovery Time Objective (RTO) and Recovery Point Objective
# (RPO), both of which are always in violation because the process
# runs for less than a second and the backup schedule assumes it
# runs 24/7/365. The drill is the corporate equivalent of a fire
# drill, except the building is made of RAM and the sprinkler
# system uses the same water it's trying to save.
# ================================================================


@dataclass(frozen=True)
class DrillResult:
    """Results from a Disaster Recovery drill.

    Attributes:
        drill_id: Unique identifier for this drill.
        started_at: When the drill began.
        completed_at: When the drill completed.
        success: Whether the drill succeeded.
        original_state: The state before destruction.
        recovered_state: The state after recovery.
        data_loss_keys: Keys that were lost during recovery.
        recovery_time_us: Recovery time in microseconds.
        rto_target_ms: The target RTO.
        rpo_target_ms: The target RPO.
        rto_met: Whether the RTO was met.
        rpo_met: Whether the RPO was met.
        notes: Additional drill notes.
    """

    drill_id: str
    started_at: datetime
    completed_at: datetime
    success: bool
    original_state: dict[str, Any]
    recovered_state: dict[str, Any]
    data_loss_keys: list[str]
    recovery_time_us: float
    rto_target_ms: float
    rpo_target_ms: float
    rto_met: bool
    rpo_met: bool
    notes: list[str] = field(default_factory=list)


class DRDrillRunner:
    """Executes Disaster Recovery drills.

    A DR drill follows these steps:
    1. Record the current state (the "before" picture)
    2. Intentionally destroy the state (the "disaster")
    3. Attempt recovery using PITR or the latest backup
    4. Compare recovered state against the original
    5. Measure RTO (recovery time) and RPO (data loss)
    6. Report results with the smug satisfaction of someone
       who just set fire to their own house and then put it out

    The drill always reports RTO/RPO violations because the
    process lifetime is shorter than any reasonable backup schedule.
    """

    def __init__(
        self,
        pitr_engine: PITREngine,
        backup_manager: BackupManager,
        rto_target_ms: float = 100.0,
        rpo_target_ms: float = 50.0,
        event_bus: Any = None,
    ) -> None:
        self._pitr = pitr_engine
        self._backup_manager = backup_manager
        self._rto_target_ms = rto_target_ms
        self._rpo_target_ms = rpo_target_ms
        self._event_bus = event_bus
        self._drill_history: list[DrillResult] = []

    def run_drill(self, state: dict[str, Any]) -> DrillResult:
        """Execute a disaster recovery drill.

        Args:
            state: The current state dict to use for the drill.

        Returns:
            DrillResult with detailed recovery metrics.
        """
        drill_id = f"drill-{uuid.uuid4().hex[:12]}"
        started_at = datetime.now(timezone.utc)
        notes: list[str] = []

        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.DR_DRILL_STARTED,
                payload={"drill_id": drill_id},
                source="DRDrillRunner",
            ))

        try:
            # Step 1: Record original state
            original = copy.deepcopy(state)
            notes.append(
                f"Original state captured: {len(original)} keys. "
                f"This data is about to be intentionally destroyed."
            )

            # Step 2: Create a pre-drill backup
            self._backup_manager.create_backup(
                state,
                description=f"Pre-drill backup for {drill_id}",
            )
            notes.append("Pre-drill backup created. Safety net deployed (in RAM).")

            # Step 3: DESTROY the state (the disaster)
            state.clear()
            notes.append(
                "STATE DESTROYED. All data has been wiped. "
                "If this were production, careers would be ending right now."
            )

            # Step 4: Attempt recovery via PITR
            recovery_start_us = time.perf_counter() * 1_000_000
            recovered = self._pitr.recover_to_latest()
            recovery_time_us = time.perf_counter() * 1_000_000 - recovery_start_us

            notes.append(
                f"Recovery completed in {recovery_time_us:.2f}us. "
                f"That's {recovery_time_us / 1_000_000:.6f} seconds, "
                f"which is still longer than the entire process lifetime."
            )

            # Step 5: Restore state
            state.update(recovered)

            # Step 6: Compare and measure data loss
            data_loss_keys = [
                k for k in original if k not in recovered
            ]
            extra_keys = [
                k for k in recovered if k not in original
            ]

            if data_loss_keys:
                notes.append(
                    f"DATA LOSS DETECTED: {len(data_loss_keys)} keys lost: "
                    f"{data_loss_keys[:5]}{'...' if len(data_loss_keys) > 5 else ''}"
                )
            else:
                notes.append("No data loss detected. All keys recovered successfully.")

            if extra_keys:
                notes.append(
                    f"EXTRA DATA: {len(extra_keys)} unexpected keys appeared. "
                    f"Recovery created data that didn't exist before. "
                    f"This is either a miracle or a bug."
                )

            # Step 7: Check RTO/RPO
            rto_ms = recovery_time_us / 1000.0
            rto_met = rto_ms <= self._rto_target_ms
            rpo_met = len(data_loss_keys) == 0

            if not rto_met:
                notes.append(
                    f"RTO VIOLATION: {rto_ms:.2f}ms > target {self._rto_target_ms:.2f}ms. "
                    f"Recovery was slower than desired, which is always the case "
                    f"when your backup schedule assumes a 24/7 process."
                )
            else:
                notes.append(
                    f"RTO MET: {rto_ms:.2f}ms <= target {self._rto_target_ms:.2f}ms. "
                    f"Microsecond-level recovery. Enterprise excellence achieved."
                )

            if not rpo_met:
                notes.append(
                    f"RPO VIOLATION: {len(data_loss_keys)} keys lost. "
                    f"Some data was created after the last backup and is gone forever. "
                    f"(It was in RAM anyway, so 'forever' means 'until the next run'.)"
                )
            else:
                notes.append(
                    "RPO MET: Zero data loss. Every single bit recovered from RAM "
                    "to RAM, completing the circle of ephemeral redundancy."
                )

            completed_at = datetime.now(timezone.utc)
            result = DrillResult(
                drill_id=drill_id,
                started_at=started_at,
                completed_at=completed_at,
                success=True,
                original_state=original,
                recovered_state=recovered,
                data_loss_keys=data_loss_keys,
                recovery_time_us=recovery_time_us,
                rto_target_ms=self._rto_target_ms,
                rpo_target_ms=self._rpo_target_ms,
                rto_met=rto_met,
                rpo_met=rpo_met,
                notes=notes,
            )

            self._drill_history.append(result)

            if self._event_bus is not None:
                self._event_bus.publish(Event(
                    event_type=EventType.DR_DRILL_COMPLETED,
                    payload={
                        "drill_id": drill_id,
                        "success": True,
                        "recovery_time_us": recovery_time_us,
                        "rto_met": rto_met,
                        "rpo_met": rpo_met,
                        "data_loss_keys": len(data_loss_keys),
                    },
                    source="DRDrillRunner",
                ))

            return result

        except Exception as e:
            completed_at = datetime.now(timezone.utc)
            notes.append(f"DRILL FAILED: {e}")

            result = DrillResult(
                drill_id=drill_id,
                started_at=started_at,
                completed_at=completed_at,
                success=False,
                original_state=original if 'original' in dir() else {},
                recovered_state={},
                data_loss_keys=list(original.keys()) if 'original' in dir() else [],
                recovery_time_us=0,
                rto_target_ms=self._rto_target_ms,
                rpo_target_ms=self._rpo_target_ms,
                rto_met=False,
                rpo_met=False,
                notes=notes,
            )
            self._drill_history.append(result)

            if self._event_bus is not None:
                self._event_bus.publish(Event(
                    event_type=EventType.DR_DRILL_FAILED,
                    payload={
                        "drill_id": drill_id,
                        "error": str(e),
                    },
                    source="DRDrillRunner",
                ))

            return result

    @property
    def drill_history(self) -> list[DrillResult]:
        return list(self._drill_history)

    @property
    def total_drills(self) -> int:
        return len(self._drill_history)

    @property
    def successful_drills(self) -> int:
        return sum(1 for d in self._drill_history if d.success)


# ================================================================
# Recovery Dashboard
# ================================================================
# The ASCII dashboard presents a comforting visual summary of the
# disaster recovery posture, complete with WAL statistics, backup
# vault utilization, PITR capabilities, retention compliance,
# and a prominent warning that ALL BACKUPS ARE STORED IN RAM.
# ================================================================


class RecoveryDashboard:
    """Renders ASCII disaster recovery dashboards.

    Produces beautiful ASCII art summarizing the DR posture of the
    Enterprise FizzBuzz Platform. The dashboard prominently displays
    the warning that all backups are stored in RAM, which is the
    kind of transparency that enterprise customers claim to want
    but rarely appreciate.
    """

    @staticmethod
    def render(
        wal: WriteAheadLog,
        backup_manager: BackupManager,
        pitr_engine: PITREngine,
        retention_manager: RetentionManager,
        drill_runner: Optional[DRDrillRunner] = None,
        width: int = 60,
    ) -> str:
        """Render the full disaster recovery dashboard."""
        w = max(width, 50)
        inner = w - 4  # Account for "  | " prefix and " |" suffix

        lines: list[str] = []

        def hline(char: str = "-") -> str:
            return f"  +{char * (w - 2)}+"

        def row(text: str) -> str:
            return f"  | {text:<{inner}} |"

        def center_row(text: str) -> str:
            return f"  | {text:^{inner}} |"

        # Header
        lines.append(hline("="))
        lines.append(center_row("DISASTER RECOVERY DASHBOARD"))
        lines.append(center_row("Enterprise FizzBuzz Platform"))
        lines.append(hline("="))
        lines.append(row(""))
        lines.append(center_row("!!! WARNING: ALL BACKUPS STORED IN-MEMORY !!!"))
        lines.append(center_row("A process restart destroys ALL recovery data."))
        lines.append(center_row("This is by design. We are not sorry."))
        lines.append(row(""))
        lines.append(hline("-"))

        # WAL Statistics
        wal_stats = wal.get_statistics()
        lines.append(center_row("WRITE-AHEAD LOG (WAL)"))
        lines.append(hline("-"))
        lines.append(row(f"Total Entries:      {wal_stats['total_entries']}"))
        lines.append(row(f"Latest Sequence:    {wal_stats['latest_sequence']}"))
        lines.append(row(f"Max Capacity:       {wal_stats['max_entries']}"))
        lines.append(row(f"Corruption Events:  {wal_stats['corruption_count']}"))
        lines.append(row(f"Storage Location:   {wal_stats['storage_location']}"))
        lines.append(row(f"Durability:         {wal_stats['durability_guarantee']}"))

        ops = wal_stats.get("operations", {})
        if ops:
            lines.append(row(f"Operations:         {', '.join(f'{k}={v}' for k, v in ops.items())}"))

        lines.append(hline("-"))

        # Backup Vault
        backup_stats = backup_manager.get_statistics()
        lines.append(center_row("BACKUP VAULT"))
        lines.append(hline("-"))
        utilization = backup_stats['utilization_pct']
        bar_len = min(inner - 25, 30)
        filled = int(utilization / 100 * bar_len)
        bar = "#" * filled + "-" * (bar_len - filled)
        lines.append(row(f"Capacity:     {backup_stats['vault_size']}/{backup_stats['max_capacity']} [{bar}] {utilization:.0f}%"))
        lines.append(row(f"Total Created:      {backup_stats['total_backups_created']}"))
        lines.append(row(f"Total Deleted:      {backup_stats['total_backups_deleted']}"))
        lines.append(row(f"Storage Medium:     {backup_stats['storage_medium']}"))

        if backup_stats['newest_backup']:
            lines.append(row(f"Newest Backup:      {backup_stats['newest_backup'][:19]}"))

        lines.append(hline("-"))

        # PITR
        pitr_stats = pitr_engine.get_statistics()
        lines.append(center_row("POINT-IN-TIME RECOVERY (PITR)"))
        lines.append(hline("-"))
        lines.append(row(f"Total Recoveries:   {pitr_stats['total_recoveries']}"))
        avg_us = pitr_stats['average_recovery_time_us']
        lines.append(row(f"Avg Recovery Time:  {avg_us:.2f}us ({avg_us / 1000:.4f}ms)"))
        lines.append(row(f"Recovery Targets:   Any timestamp during process lifetime"))
        lines.append(row(f"Recovery Source:     Snapshot + WAL replay (both in RAM)"))
        lines.append(hline("-"))

        # Retention
        backups = [Snapshot(manifest=m, state={})
                   for m in backup_manager.list_backups()]
        # We just need manifests for summary, use the actual backup list
        actual_backups = backup_manager._vault  # Access internal for proper summary
        retention_summary = retention_manager.get_retention_summary(actual_backups)
        lines.append(center_row("RETENTION POLICY"))
        lines.append(hline("-"))

        policy = retention_summary["policy"]
        current = retention_summary["current"]

        for tier in ["hourly", "daily", "weekly", "monthly"]:
            cur = current.get(tier, 0)
            max_val = policy.get(tier, 0)
            status = "OK" if cur <= max_val else "OVER"
            lines.append(row(f"  {tier.capitalize():<12} {cur}/{max_val} [{status}]"))

        lines.append(row(f"Total Pruned:       {retention_summary['total_pruned']}"))
        lines.append(row(f"Compliance:         {retention_summary['compliance']}"))
        lines.append(hline("-"))

        # DR Drill Results
        if drill_runner is not None and drill_runner.total_drills > 0:
            lines.append(center_row("DR DRILL RESULTS"))
            lines.append(hline("-"))
            lines.append(row(f"Total Drills:       {drill_runner.total_drills}"))
            lines.append(row(f"Successful:         {drill_runner.successful_drills}"))
            fail = drill_runner.total_drills - drill_runner.successful_drills
            lines.append(row(f"Failed:             {fail}"))

            last_drill = drill_runner.drill_history[-1]
            lines.append(row(f"Last Drill:         {last_drill.drill_id}"))
            lines.append(row(f"  Recovery Time:    {last_drill.recovery_time_us:.2f}us"))
            lines.append(row(f"  RTO Met:          {'YES' if last_drill.rto_met else 'NO (VIOLATION)'}"))
            lines.append(row(f"  RPO Met:          {'YES' if last_drill.rpo_met else 'NO (VIOLATION)'}"))
            lines.append(row(f"  Data Loss:        {len(last_drill.data_loss_keys)} keys"))

            lines.append(hline("-"))

        # Footer
        lines.append(row(""))
        lines.append(center_row("Remember: RAM is temporary. Disk is also temporary."))
        lines.append(center_row("Nothing is permanent. Entropy always wins."))
        lines.append(center_row("Your FizzBuzz results are as ephemeral as joy."))
        lines.append(row(""))
        lines.append(hline("="))
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def render_backup_list(backup_manager: BackupManager, width: int = 60) -> str:
        """Render a list of all backups in the vault."""
        w = max(width, 50)
        inner = w - 4

        lines: list[str] = []

        def hline(char: str = "-") -> str:
            return f"  +{char * (w - 2)}+"

        def row(text: str) -> str:
            return f"  | {text:<{inner}} |"

        def center_row(text: str) -> str:
            return f"  | {text:^{inner}} |"

        lines.append(hline("="))
        lines.append(center_row("BACKUP VAULT INVENTORY"))
        lines.append(center_row("WARNING: All backups stored in-memory"))
        lines.append(hline("="))

        manifests = backup_manager.list_backups()

        if not manifests:
            lines.append(row("No backups in vault. The void stares back."))
        else:
            for i, m in enumerate(manifests, 1):
                lines.append(row(f"#{i:>3} {m.snapshot_id}"))
                lines.append(row(f"     Created: {m.created_at.strftime('%Y-%m-%d %H:%M:%S.%f')}"))
                lines.append(row(f"     WAL Seq: {m.wal_sequence}  Entries: {m.entry_count}  Size: {m.size_bytes}B"))
                lines.append(row(f"     Hash: {m.state_hash[:32]}..."))
                if m.description:
                    lines.append(row(f"     Desc: {m.description[:inner - 11]}"))
                if i < len(manifests):
                    lines.append(row("     " + "-" * (inner - 5)))

        lines.append(hline("-"))
        lines.append(row(f"Total backups: {len(manifests)} / {backup_manager.vault_capacity}"))
        lines.append(hline("="))
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def render_drill_report(drill_result: DrillResult, width: int = 60) -> str:
        """Render a detailed report for a single DR drill."""
        w = max(width, 50)
        inner = w - 4

        lines: list[str] = []

        def hline(char: str = "-") -> str:
            return f"  +{char * (w - 2)}+"

        def row(text: str) -> str:
            return f"  | {text:<{inner}} |"

        def center_row(text: str) -> str:
            return f"  | {text:^{inner}} |"

        status = "PASSED" if drill_result.success else "FAILED"
        lines.append(hline("="))
        lines.append(center_row(f"DR DRILL REPORT: {status}"))
        lines.append(hline("="))
        lines.append(row(f"Drill ID:         {drill_result.drill_id}"))
        lines.append(row(f"Started:          {drill_result.started_at.strftime('%H:%M:%S.%f')}"))
        lines.append(row(f"Completed:        {drill_result.completed_at.strftime('%H:%M:%S.%f')}"))
        lines.append(row(f"Recovery Time:    {drill_result.recovery_time_us:.2f}us"))
        lines.append(hline("-"))

        rto_status = "MET" if drill_result.rto_met else "VIOLATED"
        rpo_status = "MET" if drill_result.rpo_met else "VIOLATED"
        lines.append(row(f"RTO Target:       {drill_result.rto_target_ms:.2f}ms [{rto_status}]"))
        lines.append(row(f"RPO Target:       {drill_result.rpo_target_ms:.2f}ms [{rpo_status}]"))
        lines.append(row(f"Data Loss:        {len(drill_result.data_loss_keys)} keys"))
        lines.append(hline("-"))

        lines.append(center_row("DRILL NOTES"))
        lines.append(hline("-"))
        for note in drill_result.notes:
            # Word-wrap notes
            while len(note) > inner:
                lines.append(row(note[:inner]))
                note = note[inner:]
            lines.append(row(note))

        lines.append(hline("="))
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def render_retention_status(
        retention_manager: RetentionManager,
        backup_manager: BackupManager,
        width: int = 60,
    ) -> str:
        """Render the retention policy status."""
        w = max(width, 50)
        inner = w - 4

        lines: list[str] = []

        def hline(char: str = "-") -> str:
            return f"  +{char * (w - 2)}+"

        def row(text: str) -> str:
            return f"  | {text:<{inner}} |"

        def center_row(text: str) -> str:
            return f"  | {text:^{inner}} |"

        actual_backups = backup_manager._vault
        summary = retention_manager.get_retention_summary(actual_backups)

        lines.append(hline("="))
        lines.append(center_row("BACKUP RETENTION STATUS"))
        lines.append(hline("="))
        lines.append(row(""))

        policy = summary["policy"]
        current = summary["current"]

        lines.append(row(f"{'Tier':<12} {'Current':>8} {'Max':>8} {'Status':>10}"))
        lines.append(row("-" * inner))

        for tier in ["hourly", "daily", "weekly", "monthly"]:
            cur = current.get(tier, 0)
            max_val = policy.get(tier, 0)
            if cur == 0:
                status = "EMPTY"
            elif cur <= max_val:
                status = "OK"
            else:
                status = "PRUNABLE"
            lines.append(row(f"{tier.capitalize():<12} {cur:>8} {max_val:>8} {status:>10}"))

        lines.append(row("-" * inner))
        total_cur = sum(current.values())
        total_max = policy["total_slots"]
        lines.append(row(f"{'Total':<12} {total_cur:>8} {total_max:>8}"))
        lines.append(row(""))
        lines.append(row(f"Compliance: {summary['compliance']}"))
        lines.append(row(f"Total Pruned: {summary['total_pruned']}"))
        lines.append(row(""))
        lines.append(center_row("NOTE: All retention tiers are meaningless for"))
        lines.append(center_row("a process that runs for less than 1 second."))
        lines.append(center_row("The retention policy exists purely for show."))
        lines.append(hline("="))
        lines.append("")

        return "\n".join(lines)


# ================================================================
# DR Middleware
# ================================================================
# The DRMiddleware sits in the middleware pipeline at priority 8
# and appends a WAL entry for every number processed. This ensures
# that every FizzBuzz evaluation is logged in the Write-Ahead Log,
# providing a comprehensive audit trail of modulo operations that
# will be lost the moment the process exits.
# ================================================================


class DRMiddleware(IMiddleware):
    """Middleware that records FizzBuzz evaluations in the Write-Ahead Log.

    Sits at priority 8 in the middleware pipeline, after validation
    and timing but before most business-logic middleware. Every number
    that passes through the pipeline gets a WAL entry, because in
    enterprise disaster recovery, no modulo operation should go
    unlogged, even if the log is stored in the same volatile RAM
    that the operation happens in.
    """

    def __init__(
        self,
        wal: WriteAheadLog,
        backup_manager: BackupManager,
        auto_snapshot_interval: int = 10,
        event_bus: Any = None,
    ) -> None:
        self._wal = wal
        self._backup_manager = backup_manager
        self._auto_snapshot_interval = auto_snapshot_interval
        self._event_bus = event_bus
        self._evaluation_count: int = 0
        self._state: dict[str, Any] = {}

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Record the evaluation in the WAL, then invoke the next handler."""
        # Let the pipeline process first
        result = next_handler(context)

        # Record the evaluation in the WAL
        self._evaluation_count += 1
        output = ""
        if result.results:
            output = result.results[-1].output

        self._wal.append(
            operation="SET",
            key=f"result_{context.number}",
            value={
                "number": context.number,
                "output": output,
                "session_id": context.session_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        # Track state for auto-snapshots
        self._state[f"result_{context.number}"] = {
            "number": context.number,
            "output": output,
        }

        # Auto-snapshot at configured intervals
        if (
            self._auto_snapshot_interval > 0
            and self._evaluation_count % self._auto_snapshot_interval == 0
        ):
            self._backup_manager.create_backup(
                self._state,
                wal_sequence=self._wal.latest_sequence,
                description=f"Auto-snapshot after {self._evaluation_count} evaluations",
            )

        return result

    def get_name(self) -> str:
        return "DRMiddleware"

    def get_priority(self) -> int:
        return 8

    @property
    def state(self) -> dict[str, Any]:
        """The current tracked state dict."""
        return self._state

    @property
    def evaluation_count(self) -> int:
        return self._evaluation_count


# ================================================================
# Disaster Recovery System (Facade)
# ================================================================
# The DRSystem is the facade that ties together all DR components:
# WAL, SnapshotEngine, BackupManager, PITREngine, RetentionManager,
# DRDrillRunner, and RecoveryDashboard. Because a disaster recovery
# subsystem is not truly enterprise-grade unless it has a facade
# pattern wrapping a strategy pattern wrapping a factory pattern.
# ================================================================


class DRSystem:
    """Facade for the Disaster Recovery subsystem.

    Provides a unified interface to the WAL, backup, PITR, retention,
    and drill subsystems. This is the one class to rule them all,
    the single entry point through which all disaster recovery
    operations must flow, because direct access to subsystems is
    the kind of architectural anarchy that leads to spaghetti code
    and production incidents.
    """

    def __init__(
        self,
        wal_max_entries: int = 10000,
        wal_verify_on_read: bool = True,
        backup_max_snapshots: int = 50,
        auto_snapshot_interval: int = 10,
        retention_hourly: int = 24,
        retention_daily: int = 7,
        retention_weekly: int = 4,
        retention_monthly: int = 12,
        rto_target_ms: float = 100.0,
        rpo_target_ms: float = 50.0,
        dashboard_width: int = 60,
        event_bus: Any = None,
    ) -> None:
        self._event_bus = event_bus
        self._dashboard_width = dashboard_width

        self.wal = WriteAheadLog(
            max_entries=wal_max_entries,
            verify_on_read=wal_verify_on_read,
            event_bus=event_bus,
        )

        self.snapshot_engine = SnapshotEngine(event_bus=event_bus)

        self.backup_manager = BackupManager(
            max_snapshots=backup_max_snapshots,
            snapshot_engine=self.snapshot_engine,
            event_bus=event_bus,
        )

        self.pitr_engine = PITREngine(
            wal=self.wal,
            backup_manager=self.backup_manager,
            snapshot_engine=self.snapshot_engine,
            event_bus=event_bus,
        )

        self.retention_policy = RetentionPolicy(
            hourly=retention_hourly,
            daily=retention_daily,
            weekly=retention_weekly,
            monthly=retention_monthly,
        )

        self.retention_manager = RetentionManager(
            policy=self.retention_policy,
            event_bus=event_bus,
        )

        self.drill_runner = DRDrillRunner(
            pitr_engine=self.pitr_engine,
            backup_manager=self.backup_manager,
            rto_target_ms=rto_target_ms,
            rpo_target_ms=rpo_target_ms,
            event_bus=event_bus,
        )

        self._auto_snapshot_interval = auto_snapshot_interval

    def create_middleware(self) -> DRMiddleware:
        """Create a DRMiddleware wired to this system's components."""
        return DRMiddleware(
            wal=self.wal,
            backup_manager=self.backup_manager,
            auto_snapshot_interval=self._auto_snapshot_interval,
            event_bus=self._event_bus,
        )

    def create_backup(
        self,
        state: dict[str, Any],
        description: str = "",
    ) -> Snapshot:
        """Create a backup of the given state."""
        return self.backup_manager.create_backup(
            state,
            wal_sequence=self.wal.latest_sequence,
            description=description,
        )

    def restore_latest(self) -> dict[str, Any]:
        """Restore the latest backup."""
        latest = self.backup_manager.get_latest_backup()
        if latest is None:
            return {}
        return self.snapshot_engine.restore_snapshot(latest)

    def pitr_recover(self, target_time: datetime) -> dict[str, Any]:
        """Point-in-Time Recovery to a specific timestamp."""
        return self.pitr_engine.recover_to_time(target_time)

    def run_drill(self, state: dict[str, Any]) -> DrillResult:
        """Execute a DR drill against the given state."""
        return self.drill_runner.run_drill(state)

    def apply_retention(self) -> None:
        """Apply the retention policy to the backup vault."""
        kept = self.retention_manager.apply(self.backup_manager._vault)
        self.backup_manager._vault = kept

    def render_dashboard(self) -> str:
        """Render the full DR dashboard."""
        return RecoveryDashboard.render(
            wal=self.wal,
            backup_manager=self.backup_manager,
            pitr_engine=self.pitr_engine,
            retention_manager=self.retention_manager,
            drill_runner=self.drill_runner,
            width=self._dashboard_width,
        )

    def render_backup_list(self) -> str:
        """Render the backup vault inventory."""
        return RecoveryDashboard.render_backup_list(
            backup_manager=self.backup_manager,
            width=self._dashboard_width,
        )

    def render_retention_status(self) -> str:
        """Render the retention policy status."""
        return RecoveryDashboard.render_retention_status(
            retention_manager=self.retention_manager,
            backup_manager=self.backup_manager,
            width=self._dashboard_width,
        )
