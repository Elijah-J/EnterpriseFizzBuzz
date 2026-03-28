"""
Enterprise FizzBuzz Platform - FizzAudit Tamper-Evident Audit Trail Test Suite

Comprehensive tests for the tamper-evident audit trail system that ensures
every action within the Enterprise FizzBuzz Platform is cryptographically
chained, immutably recorded, and queryable. Regulatory compliance demands
that no FizzBuzz evaluation can be silently altered after the fact. The
hash chain guarantees detection of any post-hoc modifications to the
historical record.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzaudit import (
    FIZZAUDIT_VERSION,
    MIDDLEWARE_PRIORITY,
    AuditEntry,
    AuditEventType,
    AuditLog,
    AuditQueryEngine,
    AuditRetentionPolicy,
    AuditSeverity,
    FizzAuditConfig,
    FizzAuditDashboard,
    FizzAuditMiddleware,
    HashChainVerifier,
    create_fizzaudit_subsystem,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def audit_log():
    """A fresh audit log instance for isolated test execution."""
    return AuditLog()


@pytest.fixture
def populated_log():
    """An audit log pre-loaded with a representative set of entries."""
    log = AuditLog()
    log.append(
        event_type=AuditEventType.LOGIN,
        actor="alice",
        resource="session",
        action="authenticate",
        details={"method": "password"},
        severity=AuditSeverity.INFO,
    )
    log.append(
        event_type=AuditEventType.EVALUATE,
        actor="alice",
        resource="fizzbuzz/15",
        action="evaluate",
        details={"input": 15, "output": "FizzBuzz"},
        severity=AuditSeverity.INFO,
    )
    log.append(
        event_type=AuditEventType.UPDATE,
        actor="bob",
        resource="config/rules",
        action="modify",
        details={"field": "divisor", "old": 3, "new": 5},
        severity=AuditSeverity.WARNING,
    )
    log.append(
        event_type=AuditEventType.DELETE,
        actor="alice",
        resource="cache/entry/42",
        action="invalidate",
        details={"reason": "stale"},
        severity=AuditSeverity.CRITICAL,
    )
    return log


@pytest.fixture
def verifier():
    """A HashChainVerifier instance."""
    return HashChainVerifier()


@pytest.fixture
def query_engine():
    """An AuditQueryEngine instance."""
    return AuditQueryEngine()


@pytest.fixture
def retention_policy():
    """An AuditRetentionPolicy instance."""
    return AuditRetentionPolicy()


# ============================================================
# TestConstants
# ============================================================


class TestConstants:
    """Verify exported constants match the documented specification."""

    def test_fizzaudit_version(self):
        """The module version must be 1.0.0 as per the initial release spec."""
        assert FIZZAUDIT_VERSION == "1.0.0"

    def test_middleware_priority(self):
        """Middleware priority 142 positions FizzAudit correctly in the pipeline."""
        assert MIDDLEWARE_PRIORITY == 142


# ============================================================
# TestAuditLog
# ============================================================


class TestAuditLog:
    """Tests for the core AuditLog, the central ledger of all platform events."""

    def test_append_creates_entry_with_hash(self, audit_log):
        """Every appended entry must receive a non-empty SHA-256 hash."""
        entry = audit_log.append(
            event_type=AuditEventType.CREATE,
            actor="admin",
            resource="rule/fizz",
            action="create",
            details={"divisor": 3, "label": "Fizz"},
            severity=AuditSeverity.INFO,
        )
        assert isinstance(entry, AuditEntry)
        assert entry.hash is not None
        assert len(entry.hash) == 64  # SHA-256 hex digest length
        assert entry.actor == "admin"
        assert entry.event_type == AuditEventType.CREATE

    def test_sequential_hashes_chain(self, audit_log):
        """Each entry's hash must depend on the previous entry's hash,
        forming a tamper-evident chain. This is the fundamental guarantee
        of the audit trail."""
        entry1 = audit_log.append(
            event_type=AuditEventType.CREATE,
            actor="admin",
            resource="rule/fizz",
            action="create",
            details={"divisor": 3},
            severity=AuditSeverity.INFO,
        )
        entry2 = audit_log.append(
            event_type=AuditEventType.EVALUATE,
            actor="engine",
            resource="fizzbuzz/3",
            action="evaluate",
            details={"result": "Fizz"},
            severity=AuditSeverity.INFO,
        )
        # The second entry must reference the first entry's hash
        assert entry2.previous_hash == entry1.hash
        # And its own hash must differ from the first
        assert entry2.hash != entry1.hash

    def test_get_entry_by_id(self, populated_log):
        """Entries must be retrievable by their unique entry_id."""
        entry = populated_log.append(
            event_type=AuditEventType.SYSTEM,
            actor="system",
            resource="heartbeat",
            action="ping",
            details={},
            severity=AuditSeverity.INFO,
        )
        retrieved = populated_log.get_entry(entry.entry_id)
        assert retrieved is not None
        assert retrieved.entry_id == entry.entry_id
        assert retrieved.hash == entry.hash

    def test_get_entries_range(self, populated_log):
        """get_entries must return entries within the specified time range."""
        now = datetime.utcnow()
        past = now - timedelta(hours=1)
        future = now + timedelta(hours=1)
        entries = populated_log.get_entries(start=past, end=future)
        assert len(entries) == 4  # All entries from populated_log

    def test_search_by_actor(self, populated_log):
        """Search must filter entries by actor identity."""
        alice_entries = populated_log.search(actor="alice")
        assert len(alice_entries) == 3  # LOGIN, EVALUATE, DELETE
        for entry in alice_entries:
            assert entry.actor == "alice"

    def test_search_by_event_type(self, populated_log):
        """Search must filter entries by event type classification."""
        update_entries = populated_log.search(event_type=AuditEventType.UPDATE)
        assert len(update_entries) == 1
        assert update_entries[0].actor == "bob"
        assert update_entries[0].event_type == AuditEventType.UPDATE

    def test_verify_chain_intact(self, populated_log):
        """An unmodified log must pass chain verification."""
        assert populated_log.verify_chain() is True

    def test_tampered_entry_breaks_chain(self, populated_log):
        """Modifying any entry's data after insertion must cause chain
        verification to fail. This is the core tamper-detection guarantee."""
        # Verify chain is initially valid
        assert populated_log.verify_chain() is True

        # Retrieve all entries and tamper with one in the middle
        now = datetime.utcnow()
        entries = populated_log.get_entries(
            start=now - timedelta(hours=1),
            end=now + timedelta(hours=1),
        )
        assert len(entries) >= 2

        # Directly mutate the second entry's action field to simulate tampering
        target = entries[1]
        original_action = target.action
        target.action = "TAMPERED_ACTION"

        # Chain verification must now detect the inconsistency
        assert populated_log.verify_chain() is False

        # Restore original to confirm the test is not a false positive
        target.action = original_action
        assert populated_log.verify_chain() is True


# ============================================================
# TestHashChainVerifier
# ============================================================


class TestHashChainVerifier:
    """Tests for the standalone HashChainVerifier utility."""

    def test_valid_chain(self, populated_log, verifier):
        """A properly constructed chain must pass verification."""
        now = datetime.utcnow()
        entries = populated_log.get_entries(
            start=now - timedelta(hours=1),
            end=now + timedelta(hours=1),
        )
        assert verifier.verify(entries) is True

    def test_broken_chain(self, populated_log, verifier):
        """A chain with a corrupted hash must fail verification."""
        now = datetime.utcnow()
        entries = populated_log.get_entries(
            start=now - timedelta(hours=1),
            end=now + timedelta(hours=1),
        )
        # Corrupt the hash of the second entry
        entries[1].hash = "0" * 64
        assert verifier.verify(entries) is False

    def test_empty_chain(self, verifier):
        """An empty chain is trivially valid — there is nothing to dispute."""
        assert verifier.verify([]) is True


# ============================================================
# TestAuditRetentionPolicy
# ============================================================


class TestAuditRetentionPolicy:
    """Tests for the configurable retention policy that enforces data lifecycle
    management in compliance with enterprise data governance standards."""

    def test_apply_removes_old_entries(self, audit_log, retention_policy):
        """Entries older than the retention window must be purged."""
        # Append an entry and artificially age it
        entry = audit_log.append(
            event_type=AuditEventType.SYSTEM,
            actor="system",
            resource="gc",
            action="cleanup",
            details={},
            severity=AuditSeverity.INFO,
        )
        # Force the entry's timestamp to 100 days ago
        entry.timestamp = datetime.utcnow() - timedelta(days=100)

        # Add a recent entry
        audit_log.append(
            event_type=AuditEventType.SYSTEM,
            actor="system",
            resource="heartbeat",
            action="ping",
            details={},
            severity=AuditSeverity.INFO,
        )

        retention_policy.set_retention(days=30)
        removed = retention_policy.apply(audit_log, retention_days=30)
        assert removed >= 1
        assert audit_log.get_size() >= 1  # The recent entry survives

    def test_keeps_recent_entries(self, audit_log, retention_policy):
        """Entries within the retention window must not be removed."""
        for i in range(5):
            audit_log.append(
                event_type=AuditEventType.EVALUATE,
                actor="engine",
                resource=f"fizzbuzz/{i}",
                action="evaluate",
                details={"input": i},
                severity=AuditSeverity.INFO,
            )
        initial_size = audit_log.get_size()
        removed = retention_policy.apply(audit_log, retention_days=90)
        assert removed == 0
        assert audit_log.get_size() == initial_size


# ============================================================
# TestAuditQueryEngine
# ============================================================


class TestAuditQueryEngine:
    """Tests for the AuditQueryEngine that enables structured queries
    over the audit log for compliance reporting and forensic analysis."""

    def test_query_by_filters(self, populated_log, query_engine):
        """Query must return entries matching the provided filter criteria."""
        results = query_engine.query(
            populated_log, filters={"actor": "bob"}
        )
        assert len(results) == 1
        assert results[0].actor == "bob"

    def test_count(self, populated_log, query_engine):
        """Count must return the number of matching entries without
        materializing the full result set."""
        count = query_engine.count(
            populated_log, filters={"actor": "alice"}
        )
        assert count == 3

    def test_empty_result(self, populated_log, query_engine):
        """Queries with no matches must return an empty list, not an error."""
        results = query_engine.query(
            populated_log, filters={"actor": "nonexistent_user"}
        )
        assert results == []


# ============================================================
# TestFizzAuditDashboard
# ============================================================


class TestFizzAuditDashboard:
    """Tests for the FizzAuditDashboard, which provides a human-readable
    summary of audit trail status for operational monitoring."""

    def test_render_returns_string(self, populated_log):
        """Dashboard render must produce a string representation."""
        dashboard = FizzAuditDashboard(populated_log)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_audit_info(self, populated_log):
        """Dashboard output must include meaningful audit trail information."""
        dashboard = FizzAuditDashboard(populated_log)
        output = dashboard.render()
        # Must reference audit-related terminology
        output_lower = output.lower()
        assert "audit" in output_lower or "entries" in output_lower or "log" in output_lower


# ============================================================
# TestFizzAuditMiddleware
# ============================================================


class TestFizzAuditMiddleware:
    """Tests for the FizzAuditMiddleware that integrates the audit trail
    into the enterprise middleware pipeline."""

    def test_get_name(self):
        """Middleware must identify itself as 'fizzaudit'."""
        log = AuditLog()
        middleware = FizzAuditMiddleware(log)
        assert middleware.get_name() == "fizzaudit"

    def test_get_priority(self):
        """Middleware priority must match the module constant."""
        log = AuditLog()
        middleware = FizzAuditMiddleware(log)
        assert middleware.get_priority() == 142

    def test_process_delegates_to_next(self):
        """Middleware must invoke the next handler in the pipeline after
        recording the audit entry, preserving pipeline continuity."""
        log = AuditLog()
        middleware = FizzAuditMiddleware(log)
        ctx = MagicMock()
        next_handler = MagicMock()
        middleware.process(ctx, next_handler)
        next_handler.assert_called_once()


# ============================================================
# TestCreateSubsystem
# ============================================================


class TestCreateSubsystem:
    """Tests for the create_fizzaudit_subsystem factory function that
    provisions a fully wired audit trail subsystem."""

    def test_returns_tuple_of_three(self):
        """Factory must return a 3-tuple of (AuditLog, Dashboard, Middleware)."""
        result = create_fizzaudit_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3
        log, dashboard, middleware = result
        assert isinstance(log, AuditLog)
        assert isinstance(dashboard, FizzAuditDashboard)
        assert isinstance(middleware, FizzAuditMiddleware)

    def test_log_accepts_entries(self):
        """The provisioned log must be operational and accept entries."""
        log, _, _ = create_fizzaudit_subsystem()
        entry = log.append(
            event_type=AuditEventType.SYSTEM,
            actor="test",
            resource="subsystem",
            action="verify",
            details={"check": "operational"},
            severity=AuditSeverity.INFO,
        )
        assert entry is not None
        assert log.get_size() >= 1

    def test_chain_valid_after_creation(self):
        """The hash chain must be valid immediately after subsystem creation
        and after appending entries."""
        log, _, _ = create_fizzaudit_subsystem()
        for i in range(3):
            log.append(
                event_type=AuditEventType.EVALUATE,
                actor="engine",
                resource=f"fizzbuzz/{i}",
                action="evaluate",
                details={"input": i},
                severity=AuditSeverity.INFO,
            )
        assert log.verify_chain() is True
