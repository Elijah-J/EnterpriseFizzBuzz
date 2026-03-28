"""Tests for enterprise_fizzbuzz.infrastructure.fizzbackup"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import pytest
from enterprise_fizzbuzz.infrastructure.fizzbackup import (
    FIZZBACKUP_VERSION, MIDDLEWARE_PRIORITY, BackupType, BackupStatus, RetentionTier,
    FizzBackupConfig, BackupRecord, BackupEngine, FizzBackupDashboard,
    FizzBackupMiddleware, create_fizzbackup_subsystem,
)

@pytest.fixture
def engine():
    e, _, _ = create_fizzbackup_subsystem()
    return e

@pytest.fixture
def subsystem():
    return create_fizzbackup_subsystem()


class TestBackupEngine:
    def test_create_full(self, engine):
        b = engine.create_backup(BackupType.FULL, "test-full")
        assert b.backup_type == BackupType.FULL
        assert b.status == BackupStatus.COMPLETED
        assert b.size_bytes > 0

    def test_create_incremental(self, engine):
        b = engine.create_backup(BackupType.INCREMENTAL, "test-incr")
        assert b.backup_type == BackupType.INCREMENTAL
        assert b.parent_id != ""

    def test_create_differential(self, engine):
        b = engine.create_backup(BackupType.DIFFERENTIAL, "test-diff")
        assert b.backup_type == BackupType.DIFFERENTIAL

    def test_restore(self, engine):
        b = engine.create_backup(BackupType.FULL)
        result = engine.restore(b.backup_id)
        assert "state" in result
        assert result["state"]["platform"] == "Enterprise FizzBuzz"

    def test_restore_not_found(self, engine):
        with pytest.raises(Exception):
            engine.restore("nonexistent")

    def test_verify(self, engine):
        b = engine.create_backup(BackupType.FULL)
        assert engine.verify(b.backup_id) is True

    def test_pitr(self, engine):
        now = datetime.now(timezone.utc)
        engine.create_backup(BackupType.FULL)
        result = engine.pitr(now + timedelta(seconds=1))
        assert "target_time" in result

    def test_list_backups(self, engine):
        assert len(engine.list_backups()) >= 2  # 2 from factory

    def test_encrypted(self, engine):
        b = engine.create_backup(BackupType.FULL)
        assert b.encrypted is True

    def test_metrics(self, engine):
        m = engine.get_metrics()
        assert m.total_backups >= 2
        assert m.backups_verified >= 2

    def test_wal_segments(self, engine):
        m = engine.get_metrics()
        assert m.wal_segments_archived >= 2


class TestFizzBackupMiddleware:
    def test_get_name(self, subsystem):
        _, _, mw = subsystem
        assert mw.get_name() == "fizzbackup"

    def test_get_priority(self, subsystem):
        _, _, mw = subsystem
        assert mw.get_priority() == MIDDLEWARE_PRIORITY

    def test_process(self, subsystem):
        _, _, mw = subsystem
        ctx = MagicMock(); ctx.metadata = {}
        mw.process(ctx, None)
        assert ctx.metadata["fizzbackup_version"] == FIZZBACKUP_VERSION

    def test_render_dashboard(self, subsystem):
        _, _, mw = subsystem
        assert "FizzBackup" in mw.render_dashboard()

    def test_render_list(self, subsystem):
        _, _, mw = subsystem
        assert "bkp-" in mw.render_list()


class TestCreateSubsystem:
    def test_returns_tuple(self):
        assert len(create_fizzbackup_subsystem()) == 3

    def test_initial_backups(self):
        e, _, _ = create_fizzbackup_subsystem()
        assert len(e.list_backups()) == 2


class TestConstants:
    def test_version(self):
        assert FIZZBACKUP_VERSION == "1.0.0"
    def test_priority(self):
        assert MIDDLEWARE_PRIORITY == 138
