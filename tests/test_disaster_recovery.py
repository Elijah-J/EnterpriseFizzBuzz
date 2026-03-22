"""
Enterprise FizzBuzz Platform - Disaster Recovery Tests

Tests for the Write-Ahead Log, Snapshot Engine, Backup Manager,
Point-in-Time Recovery, Retention Manager, DR Drill Runner,
Recovery Dashboard, and DR Middleware.

Because untested disaster recovery is the same as no disaster
recovery, and no disaster recovery is the same as what we have
(everything in RAM), these tests are the only proof that any of
this works.
"""

from __future__ import annotations

import copy
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    BackupNotFoundError,
    DisasterRecoveryError,
    PITRError,
    SnapshotCreationError,
    SnapshotRestorationError,
    WALCorruptionError,
    WALReplayError,
)
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext
from enterprise_fizzbuzz.infrastructure.disaster_recovery import (
    BackupManager,
    DRDrillRunner,
    DRMiddleware,
    DRSystem,
    PITREngine,
    RecoveryDashboard,
    RetentionManager,
    RetentionPolicy,
    Snapshot,
    SnapshotEngine,
    SnapshotManifest,
    WALEntry,
    WriteAheadLog,
    _compute_wal_checksum,
)


# ================================================================
# WAL Entry Tests
# ================================================================


class TestWALEntry:
    """Tests for individual WAL entries and checksum verification."""

    def test_wal_entry_creation(self) -> None:
        """WAL entries should be created with correct checksums."""
        ts = datetime.now(timezone.utc)
        checksum = _compute_wal_checksum(1, ts, "SET", "key1", "value1")
        entry = WALEntry(
            sequence=1,
            timestamp=ts,
            operation="SET",
            key="key1",
            value="value1",
            checksum=checksum,
        )
        assert entry.sequence == 1
        assert entry.operation == "SET"
        assert entry.key == "key1"
        assert entry.value == "value1"
        assert entry.verify() is True

    def test_wal_entry_checksum_verification_passes(self) -> None:
        """Valid WAL entries should pass checksum verification."""
        ts = datetime.now(timezone.utc)
        checksum = _compute_wal_checksum(42, ts, "DELETE", "foo", None)
        entry = WALEntry(
            sequence=42,
            timestamp=ts,
            operation="DELETE",
            key="foo",
            value=None,
            checksum=checksum,
        )
        assert entry.verify() is True

    def test_wal_entry_checksum_verification_fails_on_tamper(self) -> None:
        """Tampered WAL entries should fail checksum verification."""
        ts = datetime.now(timezone.utc)
        checksum = _compute_wal_checksum(1, ts, "SET", "key1", "value1")
        # Create entry with wrong checksum
        entry = WALEntry(
            sequence=1,
            timestamp=ts,
            operation="SET",
            key="key1",
            value="value1",
            checksum="0000000000000000000000000000000000000000000000000000000000000000",
        )
        assert entry.verify() is False

    def test_wal_checksum_deterministic(self) -> None:
        """Same inputs should produce the same checksum."""
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        h1 = _compute_wal_checksum(1, ts, "SET", "k", "v")
        h2 = _compute_wal_checksum(1, ts, "SET", "k", "v")
        assert h1 == h2

    def test_wal_checksum_different_for_different_inputs(self) -> None:
        """Different inputs should produce different checksums."""
        ts = datetime.now(timezone.utc)
        h1 = _compute_wal_checksum(1, ts, "SET", "k", "v1")
        h2 = _compute_wal_checksum(1, ts, "SET", "k", "v2")
        assert h1 != h2


# ================================================================
# Write-Ahead Log Tests
# ================================================================


class TestWriteAheadLog:
    """Tests for the Write-Ahead Log."""

    def test_append_entry(self) -> None:
        """Appending to WAL should create a valid entry."""
        wal = WriteAheadLog()
        entry = wal.append("SET", "key1", "value1")
        assert entry.sequence == 1
        assert entry.operation == "SET"
        assert entry.key == "key1"
        assert entry.verify() is True

    def test_append_multiple_entries(self) -> None:
        """Multiple appends should have sequential sequence numbers."""
        wal = WriteAheadLog()
        e1 = wal.append("SET", "a", 1)
        e2 = wal.append("SET", "b", 2)
        e3 = wal.append("DELETE", "a", None)
        assert e1.sequence == 1
        assert e2.sequence == 2
        assert e3.sequence == 3
        assert wal.entry_count == 3

    def test_get_entries_all(self) -> None:
        """get_entries should return all entries when no filter."""
        wal = WriteAheadLog(verify_on_read=False)
        wal.append("SET", "a", 1)
        wal.append("SET", "b", 2)
        entries = wal.get_entries()
        assert len(entries) == 2

    def test_get_entries_since_sequence(self) -> None:
        """get_entries should filter by sequence number."""
        wal = WriteAheadLog(verify_on_read=False)
        wal.append("SET", "a", 1)
        wal.append("SET", "b", 2)
        wal.append("SET", "c", 3)
        entries = wal.get_entries(since_sequence=1)
        assert len(entries) == 2
        assert entries[0].key == "b"

    def test_wal_rotation(self) -> None:
        """WAL should rotate when max_entries is exceeded."""
        wal = WriteAheadLog(max_entries=10, verify_on_read=False)
        for i in range(15):
            wal.append("SET", f"key_{i}", i)
        # After rotation, should have about half + new entries
        assert wal.entry_count <= 10

    def test_wal_replay_set(self) -> None:
        """WAL replay should apply SET operations."""
        wal = WriteAheadLog(verify_on_read=False)
        wal.append("SET", "x", 42)
        wal.append("SET", "y", 99)
        state: dict[str, Any] = {}
        result = wal.replay(state)
        assert result["x"] == 42
        assert result["y"] == 99

    def test_wal_replay_delete(self) -> None:
        """WAL replay should apply DELETE operations."""
        wal = WriteAheadLog(verify_on_read=False)
        wal.append("SET", "x", 42)
        wal.append("DELETE", "x", None)
        state: dict[str, Any] = {}
        result = wal.replay(state)
        assert "x" not in result

    def test_wal_replay_clear(self) -> None:
        """WAL replay should apply CLEAR operations."""
        wal = WriteAheadLog(verify_on_read=False)
        wal.append("SET", "x", 42)
        wal.append("SET", "y", 99)
        wal.append("CLEAR", "", None)
        state: dict[str, Any] = {}
        result = wal.replay(state)
        assert len(result) == 0

    def test_wal_replay_unknown_operation(self) -> None:
        """WAL replay should raise WALReplayError for unknown operations."""
        wal = WriteAheadLog(verify_on_read=False)
        wal.append("EXPLODE", "x", 42)
        state: dict[str, Any] = {}
        with pytest.raises(WALReplayError):
            wal.replay(state)

    def test_wal_verify_on_read_detects_corruption(self) -> None:
        """WAL with verify_on_read should detect corrupted entries."""
        wal = WriteAheadLog(verify_on_read=True)
        entry = wal.append("SET", "x", 42)
        # Tamper with the entry by replacing it
        tampered = WALEntry(
            sequence=entry.sequence,
            timestamp=entry.timestamp,
            operation=entry.operation,
            key=entry.key,
            value="TAMPERED",
            checksum=entry.checksum,  # Old checksum won't match
            entry_id=entry.entry_id,
        )
        wal._entries[0] = tampered
        with pytest.raises(WALCorruptionError):
            wal.get_entries()

    def test_wal_statistics(self) -> None:
        """WAL statistics should include key metrics."""
        wal = WriteAheadLog()
        wal.append("SET", "a", 1)
        wal.append("SET", "b", 2)
        wal.append("DELETE", "a", None)
        stats = wal.get_statistics()
        assert stats["total_entries"] == 3
        assert stats["latest_sequence"] == 3
        assert stats["storage_location"] == "RAM (volatile)"
        assert stats["durability_guarantee"] == "None whatsoever"
        assert stats["operations"]["SET"] == 2
        assert stats["operations"]["DELETE"] == 1

    def test_wal_event_bus_integration(self) -> None:
        """WAL should publish events to the event bus."""
        event_bus = MagicMock()
        wal = WriteAheadLog(event_bus=event_bus)
        wal.append("SET", "key", "value")
        assert event_bus.publish.called


# ================================================================
# Snapshot Engine Tests
# ================================================================


class TestSnapshotEngine:
    """Tests for the Snapshot Engine."""

    def test_create_snapshot(self) -> None:
        """Creating a snapshot should deep-copy state and compute hash."""
        engine = SnapshotEngine()
        state = {"a": 1, "b": [2, 3]}
        snapshot = engine.create_snapshot(state, wal_sequence=5)
        assert snapshot.manifest.wal_sequence == 5
        assert snapshot.manifest.entry_count == 2
        assert snapshot.state == state
        # Verify deep copy
        state["a"] = 999
        assert snapshot.state["a"] == 1

    def test_create_snapshot_hash_integrity(self) -> None:
        """Snapshot hash should verify correctly on restore."""
        engine = SnapshotEngine()
        state = {"fizz": "buzz", "num": 15}
        snapshot = engine.create_snapshot(state)
        restored = engine.restore_snapshot(snapshot)
        assert restored == state

    def test_restore_snapshot_detects_corruption(self) -> None:
        """Restoring a corrupted snapshot should raise an error."""
        engine = SnapshotEngine()
        state = {"key": "value"}
        snapshot = engine.create_snapshot(state)
        # Corrupt the state
        snapshot.state["key"] = "CORRUPTED"
        with pytest.raises(SnapshotRestorationError):
            engine.restore_snapshot(snapshot)

    def test_restore_returns_deep_copy(self) -> None:
        """Restored state should be a deep copy."""
        engine = SnapshotEngine()
        state = {"list": [1, 2, 3]}
        snapshot = engine.create_snapshot(state)
        restored = engine.restore_snapshot(snapshot)
        restored["list"].append(4)
        # Original snapshot state should be unchanged
        assert len(snapshot.state["list"]) == 3

    def test_snapshot_count_increments(self) -> None:
        """Snapshot count should increment with each creation."""
        engine = SnapshotEngine()
        engine.create_snapshot({"a": 1})
        engine.create_snapshot({"b": 2})
        assert engine.total_snapshots_created == 2


# ================================================================
# Backup Manager Tests
# ================================================================


class TestBackupManager:
    """Tests for the Backup Manager."""

    def test_create_backup(self) -> None:
        """Creating a backup should add it to the vault."""
        mgr = BackupManager(max_snapshots=10)
        snap = mgr.create_backup({"x": 1})
        assert mgr.vault_size == 1
        assert snap.manifest.entry_count == 1

    def test_get_backup_by_id(self) -> None:
        """Retrieving a backup by ID should return the correct snapshot."""
        mgr = BackupManager(max_snapshots=10)
        snap = mgr.create_backup({"x": 1})
        retrieved = mgr.get_backup(snap.manifest.snapshot_id)
        assert retrieved.manifest.snapshot_id == snap.manifest.snapshot_id

    def test_get_backup_not_found(self) -> None:
        """Retrieving a non-existent backup should raise BackupNotFoundError."""
        mgr = BackupManager(max_snapshots=10)
        with pytest.raises(BackupNotFoundError):
            mgr.get_backup("nonexistent-id")

    def test_get_latest_backup(self) -> None:
        """get_latest_backup should return the most recent backup."""
        mgr = BackupManager(max_snapshots=10)
        mgr.create_backup({"a": 1})
        snap2 = mgr.create_backup({"b": 2})
        latest = mgr.get_latest_backup()
        assert latest is not None
        assert latest.manifest.snapshot_id == snap2.manifest.snapshot_id

    def test_get_latest_backup_empty_vault(self) -> None:
        """get_latest_backup should return None for empty vault."""
        mgr = BackupManager(max_snapshots=10)
        assert mgr.get_latest_backup() is None

    def test_vault_capacity_eviction(self) -> None:
        """Vault should evict oldest backup when at capacity."""
        mgr = BackupManager(max_snapshots=3)
        snap1 = mgr.create_backup({"a": 1})
        mgr.create_backup({"b": 2})
        mgr.create_backup({"c": 3})
        mgr.create_backup({"d": 4})  # Should evict snap1
        assert mgr.vault_size == 3
        with pytest.raises(BackupNotFoundError):
            mgr.get_backup(snap1.manifest.snapshot_id)

    def test_delete_backup(self) -> None:
        """Deleting a backup should remove it from the vault."""
        mgr = BackupManager(max_snapshots=10)
        snap = mgr.create_backup({"x": 1})
        mgr.delete_backup(snap.manifest.snapshot_id)
        assert mgr.vault_size == 0

    def test_delete_backup_not_found(self) -> None:
        """Deleting a non-existent backup should raise BackupNotFoundError."""
        mgr = BackupManager(max_snapshots=10)
        with pytest.raises(BackupNotFoundError):
            mgr.delete_backup("ghost-backup")

    def test_list_backups(self) -> None:
        """list_backups should return all manifests."""
        mgr = BackupManager(max_snapshots=10)
        mgr.create_backup({"a": 1})
        mgr.create_backup({"b": 2})
        manifests = mgr.list_backups()
        assert len(manifests) == 2

    def test_backup_statistics(self) -> None:
        """Statistics should reflect vault state."""
        mgr = BackupManager(max_snapshots=5)
        mgr.create_backup({"x": 1})
        mgr.create_backup({"y": 2})
        stats = mgr.get_statistics()
        assert stats["vault_size"] == 2
        assert stats["max_capacity"] == 5
        assert stats["total_backups_created"] == 2
        assert "RAM" in stats["storage_medium"]


# ================================================================
# PITR Engine Tests
# ================================================================


class TestPITREngine:
    """Tests for the Point-in-Time Recovery Engine."""

    def _make_pitr(self) -> tuple:
        """Create a PITR engine with its dependencies."""
        wal = WriteAheadLog(verify_on_read=False)
        snap_engine = SnapshotEngine()
        backup_mgr = BackupManager(max_snapshots=50, snapshot_engine=snap_engine)
        pitr = PITREngine(
            wal=wal,
            backup_manager=backup_mgr,
            snapshot_engine=snap_engine,
        )
        return pitr, wal, backup_mgr

    def test_pitr_recover_from_snapshot_and_wal(self) -> None:
        """PITR should combine snapshot + WAL replay."""
        pitr, wal, backup_mgr = self._make_pitr()

        # Create initial state and backup
        state = {"a": 1, "b": 2}
        backup_mgr.create_backup(state, wal_sequence=0)

        # Add WAL entries after snapshot
        wal.append("SET", "c", 3)
        wal.append("SET", "d", 4)

        # Recover to now
        recovered = pitr.recover_to_latest()
        assert recovered["a"] == 1
        assert recovered["b"] == 2
        assert recovered["c"] == 3
        assert recovered["d"] == 4

    def test_pitr_recover_empty_vault(self) -> None:
        """PITR with no snapshots should recover from WAL alone."""
        pitr, wal, _ = self._make_pitr()
        wal.append("SET", "x", 42)
        recovered = pitr.recover_to_latest()
        assert recovered["x"] == 42

    def test_pitr_recovery_count(self) -> None:
        """PITR should track recovery count."""
        pitr, wal, _ = self._make_pitr()
        wal.append("SET", "x", 1)
        pitr.recover_to_latest()
        pitr.recover_to_latest()
        assert pitr.recovery_count == 2

    def test_pitr_statistics(self) -> None:
        """PITR statistics should include recovery metrics."""
        pitr, wal, _ = self._make_pitr()
        wal.append("SET", "x", 1)
        pitr.recover_to_latest()
        stats = pitr.get_statistics()
        assert stats["total_recoveries"] == 1
        assert stats["average_recovery_time_us"] > 0


# ================================================================
# Retention Manager Tests
# ================================================================


class TestRetentionManager:
    """Tests for the Retention Manager."""

    def test_retention_policy_total_slots(self) -> None:
        """Retention policy should calculate total slots correctly."""
        policy = RetentionPolicy(hourly=24, daily=7, weekly=4, monthly=12)
        assert policy.total_slots == 47

    def test_retention_keeps_recent_backups(self) -> None:
        """Retention should keep recent backups within limits."""
        policy = RetentionPolicy(hourly=3, daily=2, weekly=1, monthly=1)
        mgr = RetentionManager(policy=policy)

        # Create snapshots (all within the same second = hourly tier)
        snap_engine = SnapshotEngine()
        snapshots = []
        for i in range(5):
            snap = snap_engine.create_snapshot({"i": i})
            snapshots.append(Snapshot(manifest=snap.manifest, state=snap.state))

        kept = mgr.apply(snapshots)
        # All are within "hourly" tier, so keep at most 3
        assert len(kept) <= 3

    def test_retention_summary(self) -> None:
        """Retention summary should categorize backups into tiers."""
        policy = RetentionPolicy(hourly=24, daily=7, weekly=4, monthly=12)
        mgr = RetentionManager(policy=policy)

        snap_engine = SnapshotEngine()
        snapshots = [
            Snapshot(
                manifest=snap_engine.create_snapshot({"i": i}).manifest,
                state={"i": i},
            )
            for i in range(3)
        ]

        summary = mgr.get_retention_summary(snapshots)
        assert "policy" in summary
        assert "current" in summary
        assert summary["compliance"] == "IMPOSSIBLE (process runs for <1 second)"

    def test_retention_empty_backup_list(self) -> None:
        """Retention should handle empty backup lists gracefully."""
        policy = RetentionPolicy()
        mgr = RetentionManager(policy=policy)
        kept = mgr.apply([])
        assert len(kept) == 0


# ================================================================
# DR Drill Runner Tests
# ================================================================


class TestDRDrillRunner:
    """Tests for the Disaster Recovery Drill Runner."""

    def _make_drill_runner(self) -> tuple:
        """Create a drill runner with dependencies."""
        wal = WriteAheadLog(verify_on_read=False)
        snap_engine = SnapshotEngine()
        backup_mgr = BackupManager(max_snapshots=50, snapshot_engine=snap_engine)
        pitr = PITREngine(
            wal=wal,
            backup_manager=backup_mgr,
            snapshot_engine=snap_engine,
        )
        runner = DRDrillRunner(pitr_engine=pitr, backup_manager=backup_mgr)
        return runner, wal, backup_mgr

    def test_drill_basic_success(self) -> None:
        """A basic DR drill should succeed with state recovery."""
        runner, wal, backup_mgr = self._make_drill_runner()

        state = {"fizz": "buzz", "num": 15}
        # Create a backup first
        backup_mgr.create_backup(state, wal_sequence=0)

        result = runner.run_drill(state)
        assert result.success is True
        assert result.recovery_time_us > 0
        assert len(result.notes) > 0

    def test_drill_measures_recovery_time(self) -> None:
        """Drill should measure recovery time in microseconds."""
        runner, wal, backup_mgr = self._make_drill_runner()
        state = {"a": 1}
        backup_mgr.create_backup(state)

        result = runner.run_drill(state)
        assert result.recovery_time_us > 0

    def test_drill_destroys_and_recovers_state(self) -> None:
        """Drill should destroy state, then recover it."""
        runner, wal, backup_mgr = self._make_drill_runner()
        state = {"important": "data"}
        backup_mgr.create_backup(state)

        result = runner.run_drill(state)
        # State should be restored after drill
        assert "important" in state

    def test_drill_history_tracking(self) -> None:
        """Drill runner should maintain drill history."""
        runner, wal, backup_mgr = self._make_drill_runner()
        state = {"a": 1}
        backup_mgr.create_backup(state)

        runner.run_drill(dict(state))
        runner.run_drill(dict(state))
        assert runner.total_drills == 2

    def test_drill_rto_rpo_reporting(self) -> None:
        """Drill should report RTO and RPO metrics."""
        runner, wal, backup_mgr = self._make_drill_runner()
        state = {"x": 1}
        backup_mgr.create_backup(state)

        result = runner.run_drill(state)
        assert result.rto_target_ms == 100.0
        assert result.rpo_target_ms == 50.0
        assert isinstance(result.rto_met, bool)
        assert isinstance(result.rpo_met, bool)


# ================================================================
# Recovery Dashboard Tests
# ================================================================


class TestRecoveryDashboard:
    """Tests for the Recovery Dashboard renderer."""

    def _make_components(self) -> tuple:
        """Create all DR components for dashboard rendering."""
        wal = WriteAheadLog(verify_on_read=False)
        snap_engine = SnapshotEngine()
        backup_mgr = BackupManager(max_snapshots=50, snapshot_engine=snap_engine)
        pitr = PITREngine(wal=wal, backup_manager=backup_mgr, snapshot_engine=snap_engine)
        retention_mgr = RetentionManager(policy=RetentionPolicy())
        drill_runner = DRDrillRunner(pitr_engine=pitr, backup_manager=backup_mgr)
        return wal, backup_mgr, pitr, retention_mgr, drill_runner

    def test_render_dashboard(self) -> None:
        """Dashboard should render without errors."""
        wal, backup_mgr, pitr, retention_mgr, drill_runner = self._make_components()
        wal.append("SET", "test", "data")
        backup_mgr.create_backup({"test": "data"})

        output = RecoveryDashboard.render(
            wal=wal,
            backup_manager=backup_mgr,
            pitr_engine=pitr,
            retention_manager=retention_mgr,
            drill_runner=drill_runner,
        )
        assert "DISASTER RECOVERY DASHBOARD" in output
        assert "WARNING: ALL BACKUPS STORED IN-MEMORY" in output
        assert "WRITE-AHEAD LOG" in output
        assert "BACKUP VAULT" in output
        assert "POINT-IN-TIME RECOVERY" in output
        assert "RETENTION POLICY" in output

    def test_render_dashboard_with_drill_results(self) -> None:
        """Dashboard should include drill results when available."""
        wal, backup_mgr, pitr, retention_mgr, drill_runner = self._make_components()
        state = {"a": 1}
        backup_mgr.create_backup(state)
        drill_runner.run_drill(state)

        output = RecoveryDashboard.render(
            wal=wal,
            backup_manager=backup_mgr,
            pitr_engine=pitr,
            retention_manager=retention_mgr,
            drill_runner=drill_runner,
        )
        assert "DR DRILL RESULTS" in output

    def test_render_backup_list(self) -> None:
        """Backup list should render without errors."""
        backup_mgr = BackupManager(max_snapshots=10)
        backup_mgr.create_backup({"a": 1})
        backup_mgr.create_backup({"b": 2})

        output = RecoveryDashboard.render_backup_list(backup_mgr)
        assert "BACKUP VAULT INVENTORY" in output
        assert "WARNING: All backups stored in-memory" in output

    def test_render_backup_list_empty(self) -> None:
        """Empty backup list should render gracefully."""
        backup_mgr = BackupManager(max_snapshots=10)
        output = RecoveryDashboard.render_backup_list(backup_mgr)
        assert "void" in output.lower() or "No backups" in output

    def test_render_drill_report(self) -> None:
        """Drill report should render without errors."""
        wal = WriteAheadLog(verify_on_read=False)
        snap_engine = SnapshotEngine()
        backup_mgr = BackupManager(max_snapshots=50, snapshot_engine=snap_engine)
        pitr = PITREngine(wal=wal, backup_manager=backup_mgr, snapshot_engine=snap_engine)
        runner = DRDrillRunner(pitr_engine=pitr, backup_manager=backup_mgr)

        state = {"test": "data"}
        backup_mgr.create_backup(state)
        result = runner.run_drill(state)

        output = RecoveryDashboard.render_drill_report(result)
        assert "DR DRILL REPORT" in output
        assert "Recovery Time" in output
        assert "RTO" in output
        assert "RPO" in output

    def test_render_retention_status(self) -> None:
        """Retention status should render without errors."""
        backup_mgr = BackupManager(max_snapshots=10)
        backup_mgr.create_backup({"a": 1})
        retention_mgr = RetentionManager(policy=RetentionPolicy())

        output = RecoveryDashboard.render_retention_status(retention_mgr, backup_mgr)
        assert "BACKUP RETENTION STATUS" in output
        assert "Hourly" in output
        assert "Daily" in output
        assert "Weekly" in output
        assert "Monthly" in output


# ================================================================
# DR Middleware Tests
# ================================================================


class TestDRMiddleware:
    """Tests for the Disaster Recovery Middleware."""

    def _make_context(self, number: int = 15) -> ProcessingContext:
        """Create a test ProcessingContext."""
        return ProcessingContext(
            number=number,
            session_id="test-session-id",
        )

    def test_middleware_records_wal_entry(self) -> None:
        """Middleware should record a WAL entry for each evaluation."""
        wal = WriteAheadLog(verify_on_read=False)
        backup_mgr = BackupManager()
        mw = DRMiddleware(wal=wal, backup_manager=backup_mgr, auto_snapshot_interval=0)

        ctx = self._make_context(15)

        def next_handler(c: ProcessingContext) -> ProcessingContext:
            from enterprise_fizzbuzz.domain.models import FizzBuzzResult
            c.results.append(FizzBuzzResult(number=c.number, output="FizzBuzz"))
            return c

        result = mw.process(ctx, next_handler)
        assert wal.entry_count == 1
        assert mw.evaluation_count == 1

    def test_middleware_auto_snapshots(self) -> None:
        """Middleware should create auto-snapshots at configured intervals."""
        wal = WriteAheadLog(verify_on_read=False)
        backup_mgr = BackupManager()
        mw = DRMiddleware(wal=wal, backup_manager=backup_mgr, auto_snapshot_interval=3)

        def next_handler(c: ProcessingContext) -> ProcessingContext:
            from enterprise_fizzbuzz.domain.models import FizzBuzzResult
            c.results.append(FizzBuzzResult(number=c.number, output=str(c.number)))
            return c

        for i in range(1, 7):
            ctx = self._make_context(i)
            mw.process(ctx, next_handler)

        # Should have 2 auto-snapshots (at eval 3 and 6)
        assert backup_mgr.vault_size == 2

    def test_middleware_name_and_priority(self) -> None:
        """Middleware should have correct name and priority."""
        wal = WriteAheadLog()
        mw = DRMiddleware(wal=wal, backup_manager=BackupManager())
        assert mw.get_name() == "DRMiddleware"
        assert mw.get_priority() == 8

    def test_middleware_tracks_state(self) -> None:
        """Middleware should maintain state dict of evaluations."""
        wal = WriteAheadLog(verify_on_read=False)
        backup_mgr = BackupManager()
        mw = DRMiddleware(wal=wal, backup_manager=backup_mgr, auto_snapshot_interval=0)

        def next_handler(c: ProcessingContext) -> ProcessingContext:
            from enterprise_fizzbuzz.domain.models import FizzBuzzResult
            c.results.append(FizzBuzzResult(number=c.number, output="Fizz"))
            return c

        mw.process(self._make_context(3), next_handler)
        mw.process(self._make_context(6), next_handler)

        assert "result_3" in mw.state
        assert "result_6" in mw.state


# ================================================================
# DR System (Facade) Tests
# ================================================================


class TestDRSystem:
    """Tests for the DRSystem facade."""

    def test_system_creation(self) -> None:
        """DRSystem should create all subsystems."""
        system = DRSystem()
        assert system.wal is not None
        assert system.snapshot_engine is not None
        assert system.backup_manager is not None
        assert system.pitr_engine is not None
        assert system.retention_manager is not None
        assert system.drill_runner is not None

    def test_system_create_backup(self) -> None:
        """DRSystem should create backups."""
        system = DRSystem()
        snap = system.create_backup({"fizz": "buzz"}, description="test")
        assert snap.manifest.entry_count == 1

    def test_system_restore_latest(self) -> None:
        """DRSystem should restore latest backup."""
        system = DRSystem()
        system.create_backup({"answer": 42})
        restored = system.restore_latest()
        assert restored["answer"] == 42

    def test_system_restore_empty(self) -> None:
        """DRSystem should return empty dict when no backups."""
        system = DRSystem()
        restored = system.restore_latest()
        assert restored == {}

    def test_system_pitr_recover(self) -> None:
        """DRSystem should support PITR recovery."""
        system = DRSystem()
        system.wal.append("SET", "x", 1)
        recovered = system.pitr_recover(datetime.now(timezone.utc))
        assert recovered["x"] == 1

    def test_system_run_drill(self) -> None:
        """DRSystem should run DR drills."""
        system = DRSystem()
        state = {"data": "important"}
        system.create_backup(state)
        result = system.run_drill(state)
        assert result.success is True

    def test_system_create_middleware(self) -> None:
        """DRSystem should create middleware."""
        system = DRSystem()
        mw = system.create_middleware()
        assert isinstance(mw, DRMiddleware)

    def test_system_render_dashboard(self) -> None:
        """DRSystem should render dashboard."""
        system = DRSystem()
        system.wal.append("SET", "test", 1)
        system.create_backup({"test": 1})
        output = system.render_dashboard()
        assert "DISASTER RECOVERY DASHBOARD" in output

    def test_system_render_backup_list(self) -> None:
        """DRSystem should render backup list."""
        system = DRSystem()
        system.create_backup({"a": 1})
        output = system.render_backup_list()
        assert "BACKUP VAULT INVENTORY" in output

    def test_system_render_retention_status(self) -> None:
        """DRSystem should render retention status."""
        system = DRSystem()
        system.create_backup({"a": 1})
        output = system.render_retention_status()
        assert "BACKUP RETENTION STATUS" in output

    def test_system_apply_retention(self) -> None:
        """DRSystem should apply retention policy."""
        system = DRSystem(retention_hourly=2)
        for i in range(5):
            system.create_backup({"i": i})
        system.apply_retention()
        assert system.backup_manager.vault_size <= 2


# ================================================================
# Exception Tests
# ================================================================


class TestDRExceptions:
    """Tests for Disaster Recovery exception hierarchy."""

    def test_disaster_recovery_error_base(self) -> None:
        """DisasterRecoveryError should be a FizzBuzzError."""
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        err = DisasterRecoveryError("test error")
        assert isinstance(err, FizzBuzzError)
        assert "EFP-DR00" in str(err)

    def test_wal_corruption_error(self) -> None:
        """WALCorruptionError should include entry details."""
        err = WALCorruptionError(42, "expected_hash", "actual_hash")
        assert "42" in str(err)
        assert "EFP-DR01" in str(err)

    def test_backup_not_found_error(self) -> None:
        """BackupNotFoundError should include the backup ID."""
        err = BackupNotFoundError("snap-0042")
        assert "snap-0042" in str(err)
        assert "EFP-DR06" in str(err)

    def test_pitr_error(self) -> None:
        """PITRError should include target time and reason."""
        err = PITRError("2026-03-22T00:00:00Z", "no snapshots")
        assert "2026-03-22" in str(err)
        assert "EFP-DR07" in str(err)

    def test_all_dr_error_codes(self) -> None:
        """All DR exceptions should have unique error codes."""
        from enterprise_fizzbuzz.domain.exceptions import (
            WALReplayError,
            SnapshotCreationError,
            SnapshotRestorationError,
            BackupVaultFullError,
            RetentionPolicyError,
            DRDrillError,
            RPOViolationError,
            RTOViolationError,
            DRDashboardRenderError,
        )

        codes = set()
        exceptions = [
            DisasterRecoveryError("test"),
            WALCorruptionError(1, "a", "b"),
            WALReplayError(1, "test"),
            SnapshotCreationError("test"),
            SnapshotRestorationError("id", "reason"),
            BackupVaultFullError(10, 10),
            BackupNotFoundError("id"),
            PITRError("time", "reason"),
            RetentionPolicyError("type", "reason"),
            DRDrillError("id", "phase", "reason"),
            RPOViolationError(50.0, 100.0),
            RTOViolationError(100.0, 200.0),
            DRDashboardRenderError("reason"),
        ]

        for exc in exceptions:
            codes.add(exc.error_code)

        # All 13 exceptions should have unique error codes
        assert len(codes) == 13


# ================================================================
# Event Type Tests
# ================================================================


class TestDREventTypes:
    """Tests for DR-related EventType entries."""

    def test_all_dr_event_types_exist(self) -> None:
        """All 17 DR event types should be defined."""
        dr_events = [
            EventType.DR_WAL_ENTRY_APPENDED,
            EventType.DR_WAL_CHECKSUM_VERIFIED,
            EventType.DR_WAL_CHECKSUM_FAILED,
            EventType.DR_SNAPSHOT_CREATED,
            EventType.DR_SNAPSHOT_RESTORED,
            EventType.DR_SNAPSHOT_CORRUPTED,
            EventType.DR_BACKUP_CREATED,
            EventType.DR_BACKUP_DELETED,
            EventType.DR_BACKUP_VAULT_FULL,
            EventType.DR_PITR_STARTED,
            EventType.DR_PITR_COMPLETED,
            EventType.DR_PITR_FAILED,
            EventType.DR_RETENTION_POLICY_APPLIED,
            EventType.DR_DRILL_STARTED,
            EventType.DR_DRILL_COMPLETED,
            EventType.DR_DRILL_FAILED,
            EventType.DR_DASHBOARD_RENDERED,
        ]
        assert len(dr_events) == 17
        for evt in dr_events:
            assert isinstance(evt, EventType)
