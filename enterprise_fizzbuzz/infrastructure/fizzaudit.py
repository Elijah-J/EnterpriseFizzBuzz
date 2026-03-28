"""
Enterprise FizzBuzz Platform - FizzAudit: Tamper-Evident Audit Trail

Cryptographically chained audit log ensuring every platform action is
immutably recorded with SHA-256 hash chain integrity verification.
Each entry's hash = SHA256(previous_hash + serialized_entry), creating
a chain that detects any post-hoc modification.

Architecture reference: RFC 3161, Certificate Transparency, blockchain audit logs.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzaudit import (
    FizzAuditError, FizzAuditChainError, FizzAuditEntryNotFoundError,
    FizzAuditRetentionError, FizzAuditQueryError, FizzAuditExportError,
    FizzAuditTamperError, FizzAuditConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, FizzBuzzResult, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzaudit")

EVENT_AUDIT_RECORDED = EventType.register("FIZZAUDIT_RECORDED")
EVENT_AUDIT_TAMPER = EventType.register("FIZZAUDIT_TAMPER_DETECTED")

FIZZAUDIT_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 142
GENESIS_HASH = "0" * 64


class AuditEventType(Enum):
    CREATE = "CREATE"
    READ = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    EVALUATE = "EVALUATE"
    APPROVE = "APPROVE"
    DENY = "DENY"
    SYSTEM = "SYSTEM"

class AuditSeverity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class FizzAuditConfig:
    retention_days: int = 365
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class AuditEntry:
    entry_id: str = ""
    timestamp: Optional[datetime] = None
    event_type: AuditEventType = AuditEventType.SYSTEM
    severity: AuditSeverity = AuditSeverity.INFO
    actor: str = ""
    resource: str = ""
    action: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    hash: str = ""
    previous_hash: str = ""

    def _serializable_data(self) -> str:
        """Serialize entry data (excluding hash) for chain computation."""
        return json.dumps({
            "entry_id": self.entry_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else "",
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "actor": self.actor,
            "resource": self.resource,
            "action": self.action,
            "details": self.details,
            "previous_hash": self.previous_hash,
        }, sort_keys=True)

    def compute_hash(self) -> str:
        """Compute SHA-256 hash: H(previous_hash + entry_data)."""
        data = self.previous_hash + self._serializable_data()
        return hashlib.sha256(data.encode("utf-8")).hexdigest()


# ============================================================
# Hash Chain Verifier
# ============================================================

class HashChainVerifier:
    """Verifies the integrity of a tamper-evident hash chain."""

    def verify(self, entries: List[AuditEntry]) -> bool:
        """Verify that every entry's hash correctly chains from the previous."""
        if not entries:
            return True

        # First entry should chain from genesis
        if entries[0].previous_hash != GENESIS_HASH:
            return False
        if entries[0].hash != entries[0].compute_hash():
            return False

        for i in range(1, len(entries)):
            if entries[i].previous_hash != entries[i - 1].hash:
                return False
            if entries[i].hash != entries[i].compute_hash():
                return False

        return True


# ============================================================
# Audit Log
# ============================================================

class AuditLog:
    """Tamper-evident audit log with SHA-256 hash chain."""

    def __init__(self, config: Optional[FizzAuditConfig] = None) -> None:
        self._config = config or FizzAuditConfig()
        self._entries: List[AuditEntry] = []
        self._by_id: Dict[str, AuditEntry] = {}
        self._verifier = HashChainVerifier()

    def append(self, event_type: AuditEventType, actor: str, resource: str,
               action: str, details: Optional[Dict[str, Any]] = None,
               severity: AuditSeverity = AuditSeverity.INFO) -> AuditEntry:
        """Append a new entry to the audit log with hash chain linking."""
        previous_hash = self._entries[-1].hash if self._entries else GENESIS_HASH

        entry = AuditEntry(
            entry_id=f"aud-{uuid.uuid4().hex[:12]}",
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            severity=severity,
            actor=actor,
            resource=resource,
            action=action,
            details=details or {},
            previous_hash=previous_hash,
        )
        entry.hash = entry.compute_hash()

        self._entries.append(entry)
        self._by_id[entry.entry_id] = entry
        return entry

    def get_entry(self, entry_id: str) -> AuditEntry:
        entry = self._by_id.get(entry_id)
        if entry is None:
            raise FizzAuditEntryNotFoundError(entry_id)
        return entry

    def get_entries(self, start: Optional[datetime] = None,
                    end: Optional[datetime] = None) -> List[AuditEntry]:
        result = self._entries
        if start:
            result = [e for e in result if e.timestamp and self._compare_dt(e.timestamp, start) >= 0]
        if end:
            result = [e for e in result if e.timestamp and self._compare_dt(e.timestamp, end) <= 0]
        return result

    @staticmethod
    def _compare_dt(a: datetime, b: datetime) -> int:
        """Compare two datetimes, handling naive vs aware."""
        a_naive = a.replace(tzinfo=None) if a.tzinfo else a
        b_naive = b.replace(tzinfo=None) if b.tzinfo else b
        if a_naive < b_naive: return -1
        if a_naive > b_naive: return 1
        return 0

    def verify_chain(self) -> bool:
        """Verify the entire hash chain integrity."""
        return self._verifier.verify(self._entries)

    def search(self, actor: Optional[str] = None,
               event_type: Optional[AuditEventType] = None,
               resource: Optional[str] = None) -> List[AuditEntry]:
        result = self._entries
        if actor:
            result = [e for e in result if e.actor == actor]
        if event_type:
            result = [e for e in result if e.event_type == event_type]
        if resource:
            result = [e for e in result if e.resource == resource]
        return result

    def export_json(self) -> str:
        return json.dumps([{
            "entry_id": e.entry_id,
            "timestamp": e.timestamp.isoformat() if e.timestamp else "",
            "event_type": e.event_type.value,
            "severity": e.severity.value,
            "actor": e.actor,
            "resource": e.resource,
            "action": e.action,
            "details": e.details,
            "hash": e.hash,
            "previous_hash": e.previous_hash,
        } for e in self._entries], indent=2)

    def get_size(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> List[AuditEntry]:
        return list(self._entries)


# ============================================================
# Audit Retention Policy
# ============================================================

class AuditRetentionPolicy:
    def __init__(self, retention_days: int = 365) -> None:
        self._retention_days = retention_days

    def apply(self, log: AuditLog, retention_days: Optional[int] = None) -> int:
        days = retention_days or self._retention_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        original = log.get_size()
        log._entries = [e for e in log._entries if e.timestamp and AuditLog._compare_dt(e.timestamp, cutoff) >= 0]
        log._by_id = {e.entry_id: e for e in log._entries}
        return original - log.get_size()

    def set_retention(self, days: int) -> None:
        self._retention_days = days


# ============================================================
# Audit Query Engine
# ============================================================

class AuditQueryEngine:
    def query(self, log: AuditLog, filters: Dict[str, Any]) -> List[AuditEntry]:
        return log.search(
            actor=filters.get("actor"),
            event_type=filters.get("event_type"),
            resource=filters.get("resource"),
        )

    def count(self, log: AuditLog, filters: Dict[str, Any]) -> int:
        return len(self.query(log, filters))


# ============================================================
# Dashboard & Middleware
# ============================================================

class FizzAuditDashboard:
    def __init__(self, log: Optional[AuditLog] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._log = log
        self._width = width

    def render(self) -> str:
        lines = [
            "=" * self._width,
            "FizzAudit Tamper-Evident Audit Trail".center(self._width),
            "=" * self._width,
            f"  Version:      {FIZZAUDIT_VERSION}",
        ]
        if self._log:
            lines.append(f"  Entries:      {self._log.get_size()}")
            lines.append(f"  Chain Valid:  {self._log.verify_chain()}")
            # Last 5 entries
            for e in self._log.entries[-5:]:
                lines.append(f"  {e.entry_id} {e.event_type.value:<10} {e.actor:<15} {e.action}")
        return "\n".join(lines)


class FizzAuditMiddleware(IMiddleware):
    def __init__(self, log: Optional[AuditLog] = None,
                 dashboard: Optional[FizzAuditDashboard] = None) -> None:
        self._log = log
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzaudit"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, context: Any, next_handler: Any) -> Any:
        if self._log:
            try:
                num = getattr(context, "number", 0)
                self._log.append(AuditEventType.EVALUATE, "system", "fizzbuzz",
                                 "middleware_process", {"number": num if isinstance(num, (int, float)) else 0})
            except Exception:
                pass
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "FizzAudit not initialized"

    def render_verify(self) -> str:
        if self._log:
            valid = self._log.verify_chain()
            return f"Chain integrity: {'VALID' if valid else 'COMPROMISED'} ({self._log.get_size()} entries)"
        return "No audit log"

    def render_stats(self) -> str:
        if not self._log: return "No audit log"
        return f"Entries: {self._log.get_size()}, Chain: {'valid' if self._log.verify_chain() else 'broken'}"


# ============================================================
# Factory
# ============================================================

def create_fizzaudit_subsystem(
    retention_days: int = 365,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[AuditLog, FizzAuditDashboard, FizzAuditMiddleware]:
    config = FizzAuditConfig(retention_days=retention_days, dashboard_width=dashboard_width)
    log = AuditLog(config)

    # Seed initial audit entries
    log.append(AuditEventType.SYSTEM, "fizzaudit", "platform", "audit_system_initialized",
               {"version": FIZZAUDIT_VERSION, "modules": 152})
    log.append(AuditEventType.SYSTEM, "fizzaudit", "chain", "genesis_block_created",
               {"hash_algorithm": "SHA-256", "chain_type": "tamper-evident"})
    log.append(AuditEventType.LOGIN, "bob.mcfizzington", "auth", "operator_login",
               {"ip": "10.0.0.1", "method": "password"})

    dashboard = FizzAuditDashboard(log, dashboard_width)
    middleware = FizzAuditMiddleware(log, dashboard)

    logger.info("FizzAudit initialized: %d entries, chain=%s", log.get_size(), log.verify_chain())
    return log, dashboard, middleware
