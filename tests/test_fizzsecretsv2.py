"""Tests for enterprise_fizzbuzz.infrastructure.fizzsecretsv2"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from enterprise_fizzbuzz.infrastructure.fizzsecretsv2 import (
    FIZZSECRETSV2_VERSION,
    MIDDLEWARE_PRIORITY,
    SecretType,
    LeaseState,
    FizzSecretsV2Config,
    Secret,
    Lease,
    SecretStore,
    LeaseManager,
    DynamicSecretGenerator,
    FizzSecretsV2Dashboard,
    FizzSecretsV2Middleware,
    create_fizzsecretsv2_subsystem,
)


@pytest.fixture
def store():
    return SecretStore()


@pytest.fixture
def lease_manager():
    return LeaseManager()


@pytest.fixture
def generator():
    return DynamicSecretGenerator()


@pytest.fixture
def subsystem():
    return create_fizzsecretsv2_subsystem()


# ============================================================
# TestConstants
# ============================================================

class TestConstants:
    def test_version(self):
        assert FIZZSECRETSV2_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 182


# ============================================================
# TestSecretStore
# ============================================================

class TestSecretStore:
    def test_put_and_get(self, store):
        secret = store.put("db_password", "hunter2", SecretType.STATIC)
        assert isinstance(secret, Secret)
        assert secret.name == "db_password"
        assert secret.value == "hunter2"
        assert secret.secret_type == SecretType.STATIC
        assert secret.version == 1
        retrieved = store.get("db_password")
        assert retrieved.value == "hunter2"
        assert retrieved.secret_id == secret.secret_id

    def test_delete(self, store):
        store.put("ephemeral", "tmp_value", SecretType.STATIC)
        result = store.delete("ephemeral")
        assert result is True
        with pytest.raises(Exception):
            store.get("ephemeral")

    def test_list_secrets(self, store):
        store.put("secret_a", "val_a", SecretType.STATIC)
        store.put("secret_b", "val_b", SecretType.DYNAMIC)
        listing = store.list_secrets()
        names = [s.name for s in listing]
        assert "secret_a" in names
        assert "secret_b" in names

    def test_rotate_increments_version(self, store):
        original = store.put("rotating_key", "v1_value", SecretType.ROTATING)
        assert original.version == 1
        rotated = store.rotate("rotating_key")
        assert rotated.version == 2
        assert rotated.name == "rotating_key"
        # Rotation must actually produce a different value
        assert rotated.value != original.value

    def test_get_old_version_after_rotation(self, store):
        store.put("versioned", "first", SecretType.ROTATING)
        store.rotate("versioned")
        old = store.get_version("versioned", 1)
        assert old.version == 1
        assert old.value == "first"
        current = store.get_version("versioned", 2)
        assert current.version == 2
        assert current.value != "first"

    def test_get_not_found_raises(self, store):
        with pytest.raises(Exception):
            store.get("nonexistent_secret")


# ============================================================
# TestLeaseManager
# ============================================================

class TestLeaseManager:
    def test_grant_lease(self, lease_manager):
        lease = lease_manager.grant("db_password", "service-a", ttl=60.0)
        assert isinstance(lease, Lease)
        assert lease.secret_name == "db_password"
        assert lease.granted_to == "service-a"
        assert lease.state == LeaseState.ACTIVE
        assert lease.ttl_seconds == 60.0

    def test_revoke_lease(self, lease_manager):
        lease = lease_manager.grant("api_key", "worker-1", ttl=300.0)
        lease_manager.revoke(lease.lease_id)
        revoked = lease_manager.get_lease(lease.lease_id)
        assert revoked.state == LeaseState.REVOKED

    def test_get_lease(self, lease_manager):
        lease = lease_manager.grant("token", "client-x", ttl=120.0)
        fetched = lease_manager.get_lease(lease.lease_id)
        assert fetched.lease_id == lease.lease_id
        assert fetched.secret_name == "token"

    def test_list_active_leases(self, lease_manager):
        lease_manager.grant("secret_1", "svc-a", ttl=300.0)
        lease_manager.grant("secret_2", "svc-b", ttl=300.0)
        revokable = lease_manager.grant("secret_3", "svc-c", ttl=300.0)
        lease_manager.revoke(revokable.lease_id)
        active = lease_manager.list_active_leases()
        assert len(active) == 2
        assert all(l.state == LeaseState.ACTIVE for l in active)

    def test_expire_leases_removes_expired(self, lease_manager):
        # Grant a lease with a very short TTL that will expire immediately
        lease_manager.grant("short_lived", "ephemeral-svc", ttl=0.01)
        time.sleep(0.05)
        expired_count = lease_manager.expire_leases()
        assert expired_count >= 1
        active = lease_manager.list_active_leases()
        names = [l.secret_name for l in active]
        assert "short_lived" not in names


# ============================================================
# TestDynamicSecretGenerator
# ============================================================

class TestDynamicSecretGenerator:
    def test_generate_password(self, generator):
        password = generator.generate("password", {})
        assert isinstance(password, str)
        assert len(password) > 0

    def test_generate_token(self, generator):
        token = generator.generate("token", {})
        assert isinstance(token, str)
        assert len(token) > 0
        # Two tokens should be unique
        token2 = generator.generate("token", {})
        assert token != token2

    def test_generate_with_context(self, generator):
        result = generator.generate("key", {"length": 32})
        assert isinstance(result, str)
        assert len(result) > 0


# ============================================================
# TestFizzSecretsV2Dashboard
# ============================================================

class TestFizzSecretsV2Dashboard:
    def test_render_returns_string(self, subsystem):
        store, dashboard, _ = subsystem
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_secrets_info(self, subsystem):
        store, dashboard, _ = subsystem
        store.put("dashboard_test", "visible", SecretType.STATIC)
        output = dashboard.render()
        # Dashboard should mention secrets or the version
        assert "secret" in output.lower() or "fizzsecrets" in output.lower()


# ============================================================
# TestFizzSecretsV2Middleware
# ============================================================

class TestFizzSecretsV2Middleware:
    def test_get_name(self, subsystem):
        _, _, middleware = subsystem
        assert middleware.get_name() == "fizzsecretsv2"

    def test_get_priority(self, subsystem):
        _, _, middleware = subsystem
        assert middleware.get_priority() == 182

    def test_process_calls_next(self, subsystem):
        _, _, middleware = subsystem
        ctx = MagicMock()
        ctx.metadata = {}
        next_handler = MagicMock(return_value=ctx)
        result = middleware.process(ctx, next_handler)
        next_handler.assert_called_once_with(ctx)
        assert result is ctx


# ============================================================
# TestCreateSubsystem
# ============================================================

class TestCreateSubsystem:
    def test_returns_tuple_of_three(self):
        result = create_fizzsecretsv2_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_store_works(self):
        store, _, _ = create_fizzsecretsv2_subsystem()
        assert isinstance(store, SecretStore)
        secret = store.put("factory_test", "value123", SecretType.STATIC)
        assert store.get("factory_test").value == "value123"

    def test_has_default_secrets(self):
        store, _, _ = create_fizzsecretsv2_subsystem()
        # Factory should seed the store with at least one default secret
        listing = store.list_secrets()
        assert len(listing) >= 1
