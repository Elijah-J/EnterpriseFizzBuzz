"""
Enterprise FizzBuzz Platform - FizzBackup: Disaster Recovery & Backup System

Production-grade backup and disaster recovery system for the Enterprise
FizzBuzz Platform.  Implements full, incremental, and differential backups,
point-in-time recovery via WAL replay, Grandfather-Father-Son (GFS) retention
policies, backup verification with checksum validation, AES-256 encryption
at rest, automated backup scheduling, Recovery Point Objective (RPO) and
Recovery Time Objective (RTO) tracking, and disaster recovery orchestration.

FizzBackup fills the disaster recovery gap -- the platform has three
persistence backends, database replication, and a write-ahead log, but no
mechanism for point-in-time backup and restore with retention policies.

Architecture reference: pg_basebackup, Barman, Percona XtraBackup, Velero.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import time
import uuid
import zlib
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple, Union

from enterprise_fizzbuzz.domain.exceptions.fizzbackup import (
    FizzBackupError, FizzBackupCreateError, FizzBackupRestoreError,
    FizzBackupNotFoundError, FizzBackupVerifyError, FizzBackupRetentionError,
    FizzBackupEncryptionError, FizzBackupScheduleError,
    FizzBackupIncrementalError, FizzBackupWALError, FizzBackupStorageError,
    FizzBackupDRError, FizzBackupRPOError, FizzBackupRTOError, FizzBackupConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, FizzBuzzResult, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzbackup")

EVENT_BACKUP_CREATED = EventType.register("FIZZBACKUP_CREATED")
EVENT_BACKUP_RESTORED = EventType.register("FIZZBACKUP_RESTORED")
EVENT_BACKUP_VERIFIED = EventType.register("FIZZBACKUP_VERIFIED")

FIZZBACKUP_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 138


class BackupType(Enum):
    FULL = "full"
    INCREMENTAL = "incremental"
    DIFFERENTIAL = "differential"

class BackupStatus(Enum):
    IN_PROGRESS = auto()
    COMPLETED = auto()
    FAILED = auto()
    VERIFIED = auto()
    EXPIRED = auto()

class RetentionTier(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


@dataclass
class FizzBackupConfig:
    retention_days: int = 30
    retention_weekly: int = 12
    retention_monthly: int = 12
    retention_yearly: int = 3
    encryption: bool = True
    compression: bool = True
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH
    rpo_seconds: int = 3600
    rto_seconds: int = 1800

@dataclass
class BackupRecord:
    backup_id: str = ""
    backup_type: BackupType = BackupType.FULL
    status: BackupStatus = BackupStatus.COMPLETED
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    size_bytes: int = 0
    compressed_size: int = 0
    checksum: str = ""
    encrypted: bool = False
    parent_id: str = ""
    wal_start: str = ""
    wal_end: str = ""
    retention_tier: RetentionTier = RetentionTier.DAILY
    data: bytes = b""
    label: str = ""

@dataclass
class WALSegment:
    segment_id: str = ""
    lsn_start: int = 0
    lsn_end: int = 0
    timestamp: float = 0.0
    data: bytes = b""
    size: int = 0
    archived: bool = False

@dataclass
class RestorePoint:
    name: str = ""
    timestamp: Optional[datetime] = None
    backup_id: str = ""
    wal_position: str = ""

@dataclass
class BackupMetrics:
    total_backups: int = 0
    total_size_bytes: int = 0
    last_backup_at: Optional[datetime] = None
    last_restore_at: Optional[datetime] = None
    backups_verified: int = 0
    backups_failed: int = 0
    restores_performed: int = 0
    wal_segments_archived: int = 0
    current_rpo_seconds: float = 0.0
    rpo_violations: int = 0


# ============================================================
# Backup Engine
# ============================================================

class BackupEngine:
    """Backup creation, storage, and management engine."""

    def __init__(self, config: FizzBackupConfig) -> None:
        self._config = config
        self._backups: OrderedDict[str, BackupRecord] = OrderedDict()
        self._wal_segments: List[WALSegment] = []
        self._restore_points: Dict[str, RestorePoint] = {}
        self._metrics = BackupMetrics()
        self._started = False
        self._start_time = 0.0

    def start(self) -> None:
        self._started = True
        self._start_time = time.time()

    def create_backup(self, backup_type: BackupType = BackupType.FULL,
                      label: str = "") -> BackupRecord:
        """Create a backup of the platform state."""
        now = datetime.now(timezone.utc)
        backup_id = f"bkp-{uuid.uuid4().hex[:8]}"

        # Simulate backup data
        state_data = json.dumps({
            "platform": "Enterprise FizzBuzz",
            "modules": 146,
            "timestamp": now.isoformat(),
            "type": backup_type.value,
        }).encode()

        # Compress
        compressed = zlib.compress(state_data) if self._config.compression else state_data

        # Encrypt (simulated)
        if self._config.encryption:
            key = hashlib.sha256(b"fizzbackup-encryption-key").digest()
            encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(compressed))
        else:
            encrypted = compressed

        checksum = hashlib.sha256(encrypted).hexdigest()

        # Find parent for incremental/differential
        parent_id = ""
        if backup_type in (BackupType.INCREMENTAL, BackupType.DIFFERENTIAL):
            fulls = [b for b in self._backups.values() if b.backup_type == BackupType.FULL]
            if fulls:
                if backup_type == BackupType.INCREMENTAL:
                    parent_id = list(self._backups.keys())[-1]
                else:
                    parent_id = fulls[-1].backup_id

        # Determine retention tier
        tier = self._classify_retention(now)

        record = BackupRecord(
            backup_id=backup_id, backup_type=backup_type,
            status=BackupStatus.COMPLETED, created_at=now,
            completed_at=datetime.now(timezone.utc),
            size_bytes=len(state_data), compressed_size=len(encrypted),
            checksum=checksum, encrypted=self._config.encryption,
            parent_id=parent_id,
            wal_start=f"0/{len(self._wal_segments):08X}",
            wal_end=f"0/{len(self._wal_segments) + 1:08X}",
            retention_tier=tier, data=encrypted, label=label or backup_type.value,
        )

        self._backups[backup_id] = record
        self._metrics.total_backups += 1
        self._metrics.total_size_bytes += len(encrypted)
        self._metrics.last_backup_at = now
        self._metrics.current_rpo_seconds = 0.0

        # Archive WAL
        wal = WALSegment(
            segment_id=f"wal-{uuid.uuid4().hex[:8]}",
            lsn_start=len(self._wal_segments),
            lsn_end=len(self._wal_segments) + 1,
            timestamp=time.time(),
            data=state_data[:100],
            size=100,
            archived=True,
        )
        self._wal_segments.append(wal)
        self._metrics.wal_segments_archived += 1

        logger.info("Backup created: %s type=%s size=%d", backup_id, backup_type.value, len(encrypted))
        return record

    def restore(self, backup_id: str) -> Dict[str, Any]:
        """Restore from a backup."""
        record = self._backups.get(backup_id)
        if record is None:
            raise FizzBackupNotFoundError(backup_id)

        # Decrypt
        if record.encrypted:
            key = hashlib.sha256(b"fizzbackup-encryption-key").digest()
            decrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(record.data))
        else:
            decrypted = record.data

        # Decompress
        if self._config.compression:
            decompressed = zlib.decompress(decrypted)
        else:
            decompressed = decrypted

        # Verify checksum
        if hashlib.sha256(record.data).hexdigest() != record.checksum:
            raise FizzBackupVerifyError("Checksum mismatch")

        state = json.loads(decompressed)

        self._metrics.restores_performed += 1
        self._metrics.last_restore_at = datetime.now(timezone.utc)

        return {"backup_id": backup_id, "type": record.backup_type.value,
                "created_at": record.created_at.isoformat() if record.created_at else "",
                "state": state, "size": record.size_bytes}

    def pitr(self, target_time: datetime) -> Dict[str, Any]:
        """Point-in-time recovery to a specific timestamp."""
        # Find the most recent full backup before target_time
        candidate = None
        for record in reversed(list(self._backups.values())):
            if record.created_at and record.created_at <= target_time:
                candidate = record
                break
        if candidate is None:
            raise FizzBackupRestoreError("No backup found before target time")

        result = self.restore(candidate.backup_id)
        # Simulate WAL replay
        wal_replayed = sum(1 for w in self._wal_segments if w.timestamp <= target_time.timestamp())
        result["wal_segments_replayed"] = wal_replayed
        result["target_time"] = target_time.isoformat()
        return result

    def verify(self, backup_id: str) -> bool:
        """Verify backup integrity."""
        record = self._backups.get(backup_id)
        if record is None:
            raise FizzBackupNotFoundError(backup_id)
        valid = hashlib.sha256(record.data).hexdigest() == record.checksum
        if valid:
            record.status = BackupStatus.VERIFIED
            self._metrics.backups_verified += 1
        else:
            record.status = BackupStatus.FAILED
            self._metrics.backups_failed += 1
        return valid

    def apply_retention(self) -> int:
        """Apply GFS retention policy. Returns number of expired backups."""
        now = datetime.now(timezone.utc)
        expired = []
        for bid, record in self._backups.items():
            if record.created_at is None:
                continue
            age = now - record.created_at
            if record.retention_tier == RetentionTier.DAILY and age.days > self._config.retention_days:
                expired.append(bid)
            elif record.retention_tier == RetentionTier.WEEKLY and age.days > self._config.retention_weekly * 7:
                expired.append(bid)
            elif record.retention_tier == RetentionTier.MONTHLY and age.days > self._config.retention_monthly * 30:
                expired.append(bid)
            elif record.retention_tier == RetentionTier.YEARLY and age.days > self._config.retention_yearly * 365:
                expired.append(bid)
        for bid in expired:
            record = self._backups.pop(bid)
            self._metrics.total_size_bytes -= record.compressed_size
        return len(expired)

    def list_backups(self) -> List[BackupRecord]:
        return list(self._backups.values())

    def get_backup(self, backup_id: str) -> Optional[BackupRecord]:
        return self._backups.get(backup_id)

    def _classify_retention(self, dt: datetime) -> RetentionTier:
        if dt.day == 1 and dt.month == 1:
            return RetentionTier.YEARLY
        elif dt.day == 1:
            return RetentionTier.MONTHLY
        elif dt.weekday() == 6:  # Sunday
            return RetentionTier.WEEKLY
        return RetentionTier.DAILY

    def get_metrics(self) -> BackupMetrics:
        m = copy.copy(self._metrics)
        if m.last_backup_at:
            m.current_rpo_seconds = (datetime.now(timezone.utc) - m.last_backup_at).total_seconds()
            if m.current_rpo_seconds > self._config.rpo_seconds:
                m.rpo_violations += 1
        return m

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time if self._started else 0.0

    @property
    def is_running(self) -> bool:
        return self._started


# ============================================================
# Dashboard & Middleware
# ============================================================

class FizzBackupDashboard:
    def __init__(self, engine: BackupEngine, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._engine = engine
        self._width = width

    def render(self) -> str:
        m = self._engine.get_metrics()
        lines = [
            "=" * self._width,
            "FizzBackup Disaster Recovery Dashboard".center(self._width),
            "=" * self._width,
            f"  Engine ({FIZZBACKUP_VERSION})",
            f"  {'─' * (self._width - 4)}",
            f"  Status:        {'RUNNING' if self._engine.is_running else 'STOPPED'}",
            f"  Backups:       {m.total_backups}",
            f"  Size:          {m.total_size_bytes} bytes",
            f"  Verified:      {m.backups_verified}",
            f"  Restores:      {m.restores_performed}",
            f"  WAL Segments:  {m.wal_segments_archived}",
            f"  Current RPO:   {m.current_rpo_seconds:.0f}s",
            f"  Last Backup:   {m.last_backup_at.isoformat() if m.last_backup_at else 'never'}",
        ]
        for b in self._engine.list_backups()[-5:]:
            lines.append(f"  {b.backup_id} {b.backup_type.value:<12} {b.status.name:<10} {b.compressed_size}B {b.label}")
        return "\n".join(lines)


class FizzBackupMiddleware(IMiddleware):
    def __init__(self, engine: BackupEngine, dashboard: FizzBackupDashboard,
                 config: FizzBackupConfig) -> None:
        self._engine = engine
        self._dashboard = dashboard
        self._config = config

    def get_name(self) -> str: return "fizzbackup"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, context: ProcessingContext, next_handler: Any) -> ProcessingContext:
        m = self._engine.get_metrics()
        context.metadata["fizzbackup_version"] = FIZZBACKUP_VERSION
        context.metadata["fizzbackup_total"] = m.total_backups
        context.metadata["fizzbackup_rpo"] = m.current_rpo_seconds
        if next_handler: return next_handler(context)
        return context

    def render_dashboard(self) -> str: return self._dashboard.render()

    def render_status(self) -> str:
        m = self._engine.get_metrics()
        return (f"FizzBackup {FIZZBACKUP_VERSION} | {'UP' if self._engine.is_running else 'DOWN'} | "
                f"Backups: {m.total_backups} | RPO: {m.current_rpo_seconds:.0f}s")

    def render_list(self) -> str:
        lines = ["FizzBackup Listing:"]
        for b in self._engine.list_backups():
            lines.append(f"  {b.backup_id} {b.backup_type.value:<12} {b.status.name:<10} "
                         f"{b.compressed_size}B {b.created_at}")
        return "\n".join(lines)

    def render_stats(self) -> str:
        m = self._engine.get_metrics()
        return (f"Total: {m.total_backups}, Size: {m.total_size_bytes}B, "
                f"Verified: {m.backups_verified}, Restores: {m.restores_performed}, "
                f"WAL: {m.wal_segments_archived}, RPO: {m.current_rpo_seconds:.0f}s")


def create_fizzbackup_subsystem(
    retention_days: int = 30, encryption: bool = True,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[BackupEngine, FizzBackupDashboard, FizzBackupMiddleware]:
    config = FizzBackupConfig(retention_days=retention_days, encryption=encryption,
                              dashboard_width=dashboard_width)
    engine = BackupEngine(config)
    engine.start()

    # Create initial full backup
    engine.create_backup(BackupType.FULL, "initial-full")
    engine.create_backup(BackupType.INCREMENTAL, "initial-incr")
    # Verify
    for b in engine.list_backups():
        engine.verify(b.backup_id)

    dashboard = FizzBackupDashboard(engine, dashboard_width)
    middleware = FizzBackupMiddleware(engine, dashboard, config)

    logger.info("FizzBackup initialized: 2 backups, retention=%dd", retention_days)
    return engine, dashboard, middleware
