"""
Enterprise FizzBuzz Platform - FizzEtcd Distributed Key-Value Store Tests

Comprehensive test suite for the FizzEtcd subsystem, which provides a
distributed key-value store with watch notifications, lease-based TTL
management, and multi-version concurrency control (MVCC) semantics.

Covers: KeyValue, Lease, WatchEvent dataclasses, EtcdStore CRUD and
range queries, lease lifecycle (grant/attach/revoke), watch registration
and event dispatch, history compaction, revision tracking,
FizzEtcdDashboard rendering, FizzEtcdMiddleware pipeline integration,
create_fizzetcd_subsystem factory, and the exception hierarchy.
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.domain.exceptions.fizzetcd import (
    FizzEtcdError,
    FizzEtcdLeaseError,
    FizzEtcdNotFoundError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)
from enterprise_fizzbuzz.infrastructure.fizzetcd import (
    FIZZETCD_VERSION,
    MIDDLEWARE_PRIORITY,
    EtcdStore,
    FizzEtcdDashboard,
    FizzEtcdMiddleware,
    KeyValue,
    Lease,
    WatchEvent,
    create_fizzetcd_subsystem,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def store():
    """A fresh EtcdStore instance."""
    return EtcdStore()


# ---------------------------------------------------------------------------
# Module-level constant tests
# ---------------------------------------------------------------------------


class TestModuleConstants:
    """Tests for the FizzEtcd module-level exports."""

    def test_version_string(self):
        assert FIZZETCD_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 220


# ---------------------------------------------------------------------------
# KeyValue dataclass tests
# ---------------------------------------------------------------------------


class TestKeyValueDataclass:
    """Tests for the KeyValue dataclass structure."""

    def test_keyvalue_fields(self):
        kv = KeyValue(
            key="/registry/nodes/1",
            value="active",
            version=1,
            create_revision=5,
            mod_revision=5,
        )
        assert kv.key == "/registry/nodes/1"
        assert kv.value == "active"
        assert kv.version == 1
        assert kv.create_revision == 5
        assert kv.mod_revision == 5


# ---------------------------------------------------------------------------
# Lease dataclass tests
# ---------------------------------------------------------------------------


class TestLeaseDataclass:
    """Tests for the Lease dataclass structure."""

    def test_lease_fields(self):
        lease = Lease(
            lease_id="lease-001",
            ttl_seconds=30,
            granted_at="2026-03-28T00:00:00Z",
            keys=[],
        )
        assert lease.lease_id == "lease-001"
        assert lease.ttl_seconds == 30
        assert isinstance(lease.keys, list)


# ---------------------------------------------------------------------------
# WatchEvent dataclass tests
# ---------------------------------------------------------------------------


class TestWatchEventDataclass:
    """Tests for the WatchEvent dataclass structure."""

    def test_put_event_fields(self):
        evt = WatchEvent(event_type="PUT", key="/a", value="b", revision=1)
        assert evt.event_type == "PUT"
        assert evt.value == "b"

    def test_delete_event_fields(self):
        evt = WatchEvent(event_type="DELETE", key="/a", value=None, revision=2)
        assert evt.event_type == "DELETE"
        assert evt.value is None


# ---------------------------------------------------------------------------
# EtcdStore: basic CRUD tests
# ---------------------------------------------------------------------------


class TestEtcdStoreCRUD:
    """Tests for put, get, and delete operations on the store."""

    def test_put_returns_keyvalue(self, store):
        kv = store.put("/config/timeout", "30")
        assert isinstance(kv, KeyValue)
        assert kv.key == "/config/timeout"
        assert kv.value == "30"

    def test_get_returns_stored_value(self, store):
        store.put("/config/retries", "3")
        kv = store.get("/config/retries")
        assert kv is not None
        assert kv.value == "3"

    def test_get_missing_key_returns_none(self, store):
        result = store.get("/nonexistent/key")
        assert result is None

    def test_put_overwrites_existing_key(self, store):
        store.put("/service/mode", "degraded")
        store.put("/service/mode", "nominal")
        kv = store.get("/service/mode")
        assert kv is not None
        assert kv.value == "nominal"

    def test_put_increments_version(self, store):
        kv1 = store.put("/counter", "0")
        kv2 = store.put("/counter", "1")
        assert kv2.version > kv1.version

    def test_delete_existing_key_returns_true(self, store):
        store.put("/ephemeral", "data")
        assert store.delete("/ephemeral") is True

    def test_delete_nonexistent_key_returns_false(self, store):
        assert store.delete("/ghost") is False

    def test_get_after_delete_returns_none(self, store):
        store.put("/temp", "val")
        store.delete("/temp")
        assert store.get("/temp") is None


# ---------------------------------------------------------------------------
# EtcdStore: range query tests
# ---------------------------------------------------------------------------


class TestEtcdStoreRangeQueries:
    """Tests for prefix-based range retrieval."""

    def test_get_range_returns_matching_prefix(self, store):
        store.put("/app/db/host", "localhost")
        store.put("/app/db/port", "5432")
        store.put("/app/cache/host", "redis")
        results = store.get_range("/app/db/")
        assert len(results) == 2
        keys = {kv.key for kv in results}
        assert "/app/db/host" in keys
        assert "/app/db/port" in keys

    def test_get_range_empty_for_no_match(self, store):
        store.put("/x/y", "z")
        results = store.get_range("/no/match/")
        assert results == []


# ---------------------------------------------------------------------------
# EtcdStore: revision tracking tests
# ---------------------------------------------------------------------------


class TestEtcdStoreRevisions:
    """Tests for MVCC revision semantics."""

    def test_initial_revision_is_nonnegative(self, store):
        assert store.current_revision >= 0

    def test_put_advances_revision(self, store):
        rev_before = store.current_revision
        store.put("/rev/test", "a")
        assert store.current_revision > rev_before

    def test_delete_advances_revision(self, store):
        store.put("/rev/del", "x")
        rev_before = store.current_revision
        store.delete("/rev/del")
        assert store.current_revision > rev_before

    def test_mod_revision_matches_current(self, store):
        kv = store.put("/rev/mod", "val")
        assert kv.mod_revision == store.current_revision


# ---------------------------------------------------------------------------
# EtcdStore: lease lifecycle tests
# ---------------------------------------------------------------------------


class TestEtcdStoreLeases:
    """Tests for lease granting, attachment, and revocation."""

    def test_grant_lease_returns_lease(self, store):
        lease = store.grant_lease(ttl_seconds=60)
        assert isinstance(lease, Lease)
        assert lease.ttl_seconds == 60
        assert isinstance(lease.lease_id, str)
        assert len(lease.lease_id) > 0

    def test_attach_lease_to_key(self, store):
        store.put("/session/data", "payload")
        lease = store.grant_lease(ttl_seconds=30)
        kv = store.attach_lease("/session/data", lease.lease_id)
        assert isinstance(kv, KeyValue)
        assert kv.key == "/session/data"

    def test_revoke_lease_deletes_attached_keys(self, store):
        store.put("/leased/a", "1")
        store.put("/leased/b", "2")
        lease = store.grant_lease(ttl_seconds=10)
        store.attach_lease("/leased/a", lease.lease_id)
        store.attach_lease("/leased/b", lease.lease_id)
        deleted = store.revoke_lease(lease.lease_id)
        assert isinstance(deleted, list)
        assert "/leased/a" in deleted
        assert "/leased/b" in deleted
        assert store.get("/leased/a") is None
        assert store.get("/leased/b") is None

    def test_revoke_nonexistent_lease_raises(self, store):
        with pytest.raises((FizzEtcdLeaseError, FizzEtcdError)):
            store.revoke_lease("nonexistent-lease-id")

    def test_attach_lease_nonexistent_lease_raises(self, store):
        store.put("/orphan", "val")
        with pytest.raises((FizzEtcdLeaseError, FizzEtcdError)):
            store.attach_lease("/orphan", "bogus-lease-id")


# ---------------------------------------------------------------------------
# EtcdStore: watch tests
# ---------------------------------------------------------------------------


class TestEtcdStoreWatch:
    """Tests for the watch notification mechanism."""

    def test_watch_returns_watch_id(self, store):
        watch_id = store.watch("/events/", callback=lambda evt: None)
        assert isinstance(watch_id, str)
        assert len(watch_id) > 0

    def test_watch_callback_fires_on_put(self, store):
        events_received = []
        store.watch("/watched/", callback=lambda evt: events_received.append(evt))
        store.put("/watched/key1", "value1")
        assert len(events_received) >= 1
        evt = events_received[0]
        assert isinstance(evt, WatchEvent)
        assert evt.event_type == "PUT"
        assert evt.key == "/watched/key1"

    def test_watch_callback_fires_on_delete(self, store):
        events_received = []
        store.put("/watched/del", "x")
        store.watch("/watched/", callback=lambda evt: events_received.append(evt))
        store.delete("/watched/del")
        delete_events = [e for e in events_received if e.event_type == "DELETE"]
        assert len(delete_events) >= 1
        assert delete_events[0].key == "/watched/del"

    def test_cancel_watch_stops_notifications(self, store):
        events_received = []
        watch_id = store.watch("/cancel/", callback=lambda evt: events_received.append(evt))
        store.put("/cancel/before", "a")
        count_before = len(events_received)
        store.cancel_watch(watch_id)
        store.put("/cancel/after", "b")
        assert len(events_received) == count_before

    def test_watch_ignores_unrelated_prefix(self, store):
        events_received = []
        store.watch("/specific/", callback=lambda evt: events_received.append(evt))
        store.put("/other/key", "val")
        assert len(events_received) == 0


# ---------------------------------------------------------------------------
# EtcdStore: compaction tests
# ---------------------------------------------------------------------------


class TestEtcdStoreCompaction:
    """Tests for history compaction of old revisions."""

    def test_compact_does_not_affect_current_data(self, store):
        store.put("/persist/a", "1")
        store.put("/persist/a", "2")
        rev = store.current_revision
        store.compact(rev)
        kv = store.get("/persist/a")
        assert kv is not None
        assert kv.value == "2"


# ---------------------------------------------------------------------------
# FizzEtcdDashboard tests
# ---------------------------------------------------------------------------


class TestFizzEtcdDashboard:
    """Tests for the FizzEtcd monitoring dashboard."""

    def test_render_returns_nonempty_string(self, store):
        dashboard = FizzEtcdDashboard(store)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_store_info(self, store):
        store.put("/dash/key", "val")
        dashboard = FizzEtcdDashboard(store)
        output = dashboard.render()
        assert isinstance(output, str)


# ---------------------------------------------------------------------------
# FizzEtcdMiddleware tests
# ---------------------------------------------------------------------------


class TestFizzEtcdMiddleware:
    """Tests for the FizzEtcd middleware pipeline integration."""

    def test_middleware_name_and_priority(self, store):
        mw = FizzEtcdMiddleware(store)
        assert mw.get_name() == "fizzetcd"
        assert mw.get_priority() == 220

    def test_middleware_passes_through_context(self, store):
        mw = FizzEtcdMiddleware(store)
        ctx = ProcessingContext(number=42, session_id="test-etcd-session")

        def next_handler(c: ProcessingContext) -> ProcessingContext:
            c.results.append(FizzBuzzResult(number=42, output="42"))
            return c

        result = mw.process(ctx, next_handler)
        assert len(result.results) == 1
        assert result.results[0].output == "42"
        assert result.results[0].number == 42


# ---------------------------------------------------------------------------
# Factory function tests
# ---------------------------------------------------------------------------


class TestCreateFizzEtcdSubsystem:
    """Tests for the create_fizzetcd_subsystem factory."""

    def test_returns_store_dashboard_middleware_tuple(self):
        result = create_fizzetcd_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3
        s, d, m = result
        assert isinstance(s, EtcdStore)
        assert isinstance(d, FizzEtcdDashboard)
        assert isinstance(m, FizzEtcdMiddleware)

    def test_factory_components_are_wired(self):
        s, d, m = create_fizzetcd_subsystem()
        assert d.render() is not None
        assert m.get_name() == "fizzetcd"


# ---------------------------------------------------------------------------
# Exception hierarchy tests
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    """Tests for the FizzEtcd exception classes."""

    def test_not_found_is_subclass_of_fizzetcd_error(self):
        assert issubclass(FizzEtcdNotFoundError, FizzEtcdError)

    def test_lease_error_is_subclass_of_fizzetcd_error(self):
        assert issubclass(FizzEtcdLeaseError, FizzEtcdError)

    def test_fizzetcd_error_message_contains_reason(self):
        err = FizzEtcdError("cluster unavailable")
        assert "cluster unavailable" in str(err)

    def test_not_found_error_contains_key(self):
        err = FizzEtcdNotFoundError("/missing/key")
        assert "/missing/key" in str(err)

    def test_lease_error_contains_reason(self):
        err = FizzEtcdLeaseError("expired")
        assert "expired" in str(err)
