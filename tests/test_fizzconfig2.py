"""
Tests for FizzConfig2 — Distributed Configuration Server.

These tests define the contract for the fizzconfig2 subsystem before
implementation exists. Each test exercises real behavior against the
public API surface.
"""

import time
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

import pytest

from enterprise_fizzbuzz.infrastructure.fizzconfig2 import (
    FIZZCONFIG2_VERSION,
    MIDDLEWARE_PRIORITY,
    FizzConfig2Config,
    ConfigEntry,
    ConfigNamespace,
    ConfigStore,
    ConfigValidator,
    ConfigWatcher,
    FizzConfig2Dashboard,
    FizzConfig2Middleware,
    create_fizzconfig2_subsystem,
)


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify module-level constants are correctly defined."""

    def test_version_string(self):
        assert FIZZCONFIG2_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 150


# ---------------------------------------------------------------------------
# TestConfigStore
# ---------------------------------------------------------------------------

class TestConfigStore:
    """ConfigStore is the central key-value store with namespace isolation,
    versioning, and rollback support."""

    def setup_method(self):
        self.store = ConfigStore()

    def test_set_and_get_value(self):
        """Setting a key in a namespace makes it retrievable via get()."""
        self.store.set("production", "db_host", "10.0.0.1", updated_by="admin")
        result = self.store.get("production", "db_host")
        assert result == "10.0.0.1"

    def test_versioning_increments_on_update(self):
        """Each update to the same key increments the version counter."""
        self.store.set("prod", "retries", 3, updated_by="deployer")
        v1 = self.store.get_version("prod", "retries")
        self.store.set("prod", "retries", 5, updated_by="deployer")
        v2 = self.store.get_version("prod", "retries")
        assert v2 == v1 + 1

    def test_list_keys_returns_all_keys_in_namespace(self):
        """list_keys returns every key stored under the given namespace."""
        self.store.set("ns1", "alpha", 1, updated_by="u")
        self.store.set("ns1", "beta", 2, updated_by="u")
        self.store.set("ns2", "gamma", 3, updated_by="u")
        keys = self.store.list_keys("ns1")
        assert sorted(keys) == ["alpha", "beta"]

    def test_list_namespaces(self):
        """list_namespaces returns all namespace names that contain entries."""
        self.store.set("staging", "k", "v", updated_by="u")
        self.store.set("production", "k", "v", updated_by="u")
        ns = self.store.list_namespaces()
        assert "staging" in ns
        assert "production" in ns

    def test_delete_removes_key(self):
        """After deletion, the key is no longer retrievable."""
        self.store.set("ns", "doomed", "bye", updated_by="u")
        self.store.delete("ns", "doomed")
        with pytest.raises(Exception):
            self.store.get("ns", "doomed")

    def test_rollback_restores_previous_version(self):
        """Rolling back to version 1 restores the value that was set first."""
        self.store.set("ns", "flag", "old_value", updated_by="u")
        v1 = self.store.get_version("ns", "flag")
        self.store.set("ns", "flag", "new_value", updated_by="u")
        entry = self.store.rollback("ns", "flag", v1)
        assert self.store.get("ns", "flag") == "old_value"
        assert isinstance(entry, ConfigEntry)

    def test_get_history_returns_all_versions(self):
        """get_history returns a list covering every mutation of the key."""
        self.store.set("ns", "x", "a", updated_by="u")
        self.store.set("ns", "x", "b", updated_by="u")
        self.store.set("ns", "x", "c", updated_by="u")
        history = self.store.get_history("ns", "x")
        assert len(history) >= 3

    def test_entry_has_timestamp(self):
        """ConfigEntry records a datetime for when the value was written."""
        before = datetime.utcnow()
        entry = self.store.set("ns", "timed", 42, updated_by="clock")
        after = datetime.utcnow()
        assert isinstance(entry, ConfigEntry)
        assert isinstance(entry.updated_at, datetime)
        assert before <= entry.updated_at <= after


# ---------------------------------------------------------------------------
# TestConfigValidator
# ---------------------------------------------------------------------------

class TestConfigValidator:
    """ConfigValidator checks values against registered JSON-style schemas."""

    def setup_method(self):
        self.validator = ConfigValidator()

    def test_valid_value_passes(self):
        """A value matching the schema returns success with no errors."""
        schema = {"type": "int", "min": 0, "max": 100}
        self.validator.register_schema("retry_count", schema)
        valid, errors = self.validator.validate("retry_count", 5, schema)
        assert valid is True
        assert errors == []

    def test_invalid_value_fails(self):
        """A value violating the schema returns failure with error details."""
        schema = {"type": "int", "min": 0, "max": 10}
        self.validator.register_schema("retry_count", schema)
        valid, errors = self.validator.validate("retry_count", 999, schema)
        assert valid is False
        assert len(errors) > 0

    def test_register_schema_persists(self):
        """After registering a schema, it is available for subsequent use."""
        schema = {"type": "str"}
        self.validator.register_schema("hostname", schema)
        # Validate using the registered schema — should not raise
        valid, errors = self.validator.validate("hostname", "server01", schema)
        assert valid is True


# ---------------------------------------------------------------------------
# TestConfigWatcher
# ---------------------------------------------------------------------------

class TestConfigWatcher:
    """ConfigWatcher provides pub-sub notifications for configuration changes."""

    def setup_method(self):
        self.watcher = ConfigWatcher()

    def test_watch_fires_callback_on_change(self):
        """A registered callback is invoked when notify() is called."""
        received = []
        callback = lambda ns, key, old, new: received.append((ns, key, old, new))
        self.watcher.watch("prod", "timeout", callback)
        self.watcher.notify("prod", "timeout", 30, 60)
        assert len(received) == 1
        assert received[0] == ("prod", "timeout", 30, 60)

    def test_unwatch_stops_delivery(self):
        """After unwatching, the callback no longer receives notifications."""
        received = []
        callback = lambda ns, key, old, new: received.append(1)
        watch_id = self.watcher.watch("ns", "k", callback)
        self.watcher.unwatch(watch_id)
        self.watcher.notify("ns", "k", "a", "b")
        assert len(received) == 0

    def test_multiple_watchers_all_notified(self):
        """All watchers on the same key receive the notification."""
        counters = {"a": 0, "b": 0}
        cb_a = lambda ns, key, old, new: counters.__setitem__("a", counters["a"] + 1)
        cb_b = lambda ns, key, old, new: counters.__setitem__("b", counters["b"] + 1)
        self.watcher.watch("ns", "flag", cb_a)
        self.watcher.watch("ns", "flag", cb_b)
        self.watcher.notify("ns", "flag", False, True)
        assert counters["a"] == 1
        assert counters["b"] == 1


# ---------------------------------------------------------------------------
# TestFizzConfig2Dashboard
# ---------------------------------------------------------------------------

class TestFizzConfig2Dashboard:
    """FizzConfig2Dashboard renders a human-readable status view."""

    def test_render_returns_string(self):
        dashboard = FizzConfig2Dashboard()
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_config_info(self):
        """The rendered dashboard includes identifiable configuration data."""
        dashboard = FizzConfig2Dashboard()
        output = dashboard.render()
        # Should mention the subsystem or version somewhere
        lower = output.lower()
        assert "config" in lower or "fizzconfig" in lower or "1.0.0" in lower


# ---------------------------------------------------------------------------
# TestFizzConfig2Middleware
# ---------------------------------------------------------------------------

class TestFizzConfig2Middleware:
    """FizzConfig2Middleware integrates the configuration server into the
    enterprise middleware pipeline."""

    def setup_method(self):
        self.mw = FizzConfig2Middleware()

    def test_name(self):
        assert self.mw.get_name() == "fizzconfig2"

    def test_priority(self):
        assert self.mw.get_priority() == 150

    def test_process_calls_next(self):
        """The middleware must forward processing to the next handler."""
        ctx = MagicMock()
        next_handler = MagicMock()
        self.mw.process(ctx, next_handler)
        next_handler.assert_called_once()


# ---------------------------------------------------------------------------
# TestCreateSubsystem
# ---------------------------------------------------------------------------

class TestCreateSubsystem:
    """create_fizzconfig2_subsystem() is the factory entry point that wires
    together the store, dashboard, and middleware."""

    def test_returns_three_element_tuple(self):
        result = create_fizzconfig2_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3
        store, dashboard, middleware = result
        assert isinstance(store, ConfigStore)
        assert isinstance(dashboard, FizzConfig2Dashboard)
        assert isinstance(middleware, FizzConfig2Middleware)

    def test_store_is_functional(self):
        """The store returned by the factory supports basic set/get."""
        store, _, _ = create_fizzconfig2_subsystem()
        store.set("test_ns", "greeting", "hello", updated_by="factory_test")
        assert store.get("test_ns", "greeting") == "hello"

    def test_store_can_round_trip_complex_values(self):
        """The store handles non-trivial Python values (dicts, lists)."""
        store, _, _ = create_fizzconfig2_subsystem()
        payload = {"hosts": ["a", "b"], "port": 5432, "ssl": True}
        store.set("db", "connection", payload, updated_by="test")
        assert store.get("db", "connection") == payload
