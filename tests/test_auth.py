"""
Enterprise FizzBuzz Platform - RBAC Test Suite

Comprehensive tests for the Role-Based Access Control module.
Because even access control for modulo arithmetic deserves
thorough validation — possibly more so than the arithmetic itself.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from auth import (
    AccessDeniedResponseBuilder,
    AuthorizationMiddleware,
    FizzBuzzTokenEngine,
    PermissionParser,
    RoleRegistry,
    _is_prime,
)
from config import ConfigurationManager, _SingletonMeta
from exceptions import (
    AuthenticationError,
    InsufficientFizzPrivilegesError,
    NumberClassificationLevelExceededError,
    TokenValidationError,
)
from models import (
    AuthContext,
    EventType,
    FizzBuzzRole,
    Permission,
    ProcessingContext,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield


@pytest.fixture
def secret() -> str:
    return "test-secret-for-fizzbuzz-tokens"


@pytest.fixture
def superuser_context() -> AuthContext:
    perms = RoleRegistry.get_effective_permissions(FizzBuzzRole.FIZZBUZZ_SUPERUSER)
    return AuthContext(
        user="superuser",
        role=FizzBuzzRole.FIZZBUZZ_SUPERUSER,
        token_id="test-token-id",
        effective_permissions=tuple(perms),
        trust_mode=False,
    )


@pytest.fixture
def anonymous_context() -> AuthContext:
    perms = RoleRegistry.get_effective_permissions(FizzBuzzRole.ANONYMOUS)
    return AuthContext(
        user="anonymous",
        role=FizzBuzzRole.ANONYMOUS,
        token_id=None,
        effective_permissions=tuple(perms),
        trust_mode=False,
    )


@pytest.fixture
def fizz_reader_context() -> AuthContext:
    perms = RoleRegistry.get_effective_permissions(FizzBuzzRole.FIZZ_READER)
    return AuthContext(
        user="fizz_fan",
        role=FizzBuzzRole.FIZZ_READER,
        token_id="fizz-token",
        effective_permissions=tuple(perms),
        trust_mode=False,
    )


@pytest.fixture
def buzz_admin_context() -> AuthContext:
    perms = RoleRegistry.get_effective_permissions(FizzBuzzRole.BUZZ_ADMIN)
    return AuthContext(
        user="buzz_boss",
        role=FizzBuzzRole.BUZZ_ADMIN,
        token_id="buzz-token",
        effective_permissions=tuple(perms),
        trust_mode=False,
    )


@pytest.fixture
def auditor_context() -> AuthContext:
    perms = RoleRegistry.get_effective_permissions(FizzBuzzRole.NUMBER_AUDITOR)
    return AuthContext(
        user="auditor",
        role=FizzBuzzRole.NUMBER_AUDITOR,
        token_id="audit-token",
        effective_permissions=tuple(perms),
        trust_mode=False,
    )


# ============================================================
# PermissionParser Tests
# ============================================================


class TestPermissionParser:
    def test_parse_valid_permission(self):
        perm = PermissionParser.parse("numbers:1-50:evaluate")
        assert perm.resource == "numbers"
        assert perm.range_spec == "1-50"
        assert perm.action == "evaluate"

    def test_parse_wildcard_permission(self):
        perm = PermissionParser.parse("numbers:*:read")
        assert perm.range_spec == "*"

    def test_parse_named_class_permission(self):
        perm = PermissionParser.parse("numbers:fizz:read")
        assert perm.range_spec == "fizz"

    def test_parse_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Invalid permission format"):
            PermissionParser.parse("invalid")

    def test_parse_too_few_parts_raises(self):
        with pytest.raises(ValueError):
            PermissionParser.parse("numbers:evaluate")

    def test_parse_too_many_parts_raises(self):
        with pytest.raises(ValueError):
            PermissionParser.parse("numbers:1-50:evaluate:extra")


class TestPermissionMatching:
    def test_wildcard_covers_any_number(self):
        granted = Permission(resource="numbers", range_spec="*", action="evaluate")
        required = Permission(resource="numbers", range_spec="42", action="evaluate")
        assert PermissionParser.matches(granted, required) is True

    def test_wildcard_covers_any_range(self):
        granted = Permission(resource="numbers", range_spec="*", action="evaluate")
        required = Permission(resource="numbers", range_spec="1-100", action="evaluate")
        assert PermissionParser.matches(granted, required) is True

    def test_range_covers_number_within(self):
        granted = Permission(resource="numbers", range_spec="1-50", action="evaluate")
        required = Permission(resource="numbers", range_spec="25", action="evaluate")
        assert PermissionParser.matches(granted, required) is True

    def test_range_does_not_cover_number_outside(self):
        granted = Permission(resource="numbers", range_spec="1-50", action="evaluate")
        required = Permission(resource="numbers", range_spec="51", action="evaluate")
        assert PermissionParser.matches(granted, required) is False

    def test_range_covers_boundary_start(self):
        granted = Permission(resource="numbers", range_spec="1-50", action="evaluate")
        required = Permission(resource="numbers", range_spec="1", action="evaluate")
        assert PermissionParser.matches(granted, required) is True

    def test_range_covers_boundary_end(self):
        granted = Permission(resource="numbers", range_spec="1-50", action="evaluate")
        required = Permission(resource="numbers", range_spec="50", action="evaluate")
        assert PermissionParser.matches(granted, required) is True

    def test_fizz_covers_multiple_of_3(self):
        granted = Permission(resource="numbers", range_spec="fizz", action="read")
        required = Permission(resource="numbers", range_spec="9", action="read")
        assert PermissionParser.matches(granted, required) is True

    def test_fizz_does_not_cover_non_multiple_of_3(self):
        granted = Permission(resource="numbers", range_spec="fizz", action="read")
        required = Permission(resource="numbers", range_spec="7", action="read")
        assert PermissionParser.matches(granted, required) is False

    def test_buzz_covers_multiple_of_5(self):
        granted = Permission(resource="numbers", range_spec="buzz", action="read")
        required = Permission(resource="numbers", range_spec="10", action="read")
        assert PermissionParser.matches(granted, required) is True

    def test_buzz_does_not_cover_non_multiple_of_5(self):
        granted = Permission(resource="numbers", range_spec="buzz", action="read")
        required = Permission(resource="numbers", range_spec="7", action="read")
        assert PermissionParser.matches(granted, required) is False

    def test_fizzbuzz_covers_multiple_of_15(self):
        granted = Permission(resource="numbers", range_spec="fizzbuzz", action="read")
        required = Permission(resource="numbers", range_spec="15", action="read")
        assert PermissionParser.matches(granted, required) is True

    def test_fizzbuzz_does_not_cover_multiple_of_3_only(self):
        granted = Permission(resource="numbers", range_spec="fizzbuzz", action="read")
        required = Permission(resource="numbers", range_spec="9", action="read")
        assert PermissionParser.matches(granted, required) is False

    def test_action_mismatch_denies(self):
        granted = Permission(resource="numbers", range_spec="*", action="read")
        required = Permission(resource="numbers", range_spec="1", action="evaluate")
        assert PermissionParser.matches(granted, required) is False

    def test_resource_mismatch_denies(self):
        granted = Permission(resource="other", range_spec="*", action="evaluate")
        required = Permission(resource="numbers", range_spec="1", action="evaluate")
        assert PermissionParser.matches(granted, required) is False

    def test_single_number_matches_itself(self):
        granted = Permission(resource="numbers", range_spec="1", action="read")
        required = Permission(resource="numbers", range_spec="1", action="read")
        assert PermissionParser.matches(granted, required) is True

    def test_single_number_does_not_match_other(self):
        granted = Permission(resource="numbers", range_spec="1", action="read")
        required = Permission(resource="numbers", range_spec="2", action="read")
        assert PermissionParser.matches(granted, required) is False

    def test_non_wildcard_cannot_satisfy_wildcard_required(self):
        granted = Permission(resource="numbers", range_spec="1-50", action="evaluate")
        required = Permission(resource="numbers", range_spec="*", action="evaluate")
        assert PermissionParser.matches(granted, required) is False


# ============================================================
# RoleRegistry Tests
# ============================================================


class TestRoleRegistry:
    def test_anonymous_permissions(self):
        perms = RoleRegistry.get_effective_permissions(FizzBuzzRole.ANONYMOUS)
        perm_strs = [f"{p.resource}:{p.range_spec}:{p.action}" for p in perms]
        assert "numbers:1:read" in perm_strs
        assert len(perms) == 1

    def test_fizz_reader_inherits_anonymous(self):
        perms = RoleRegistry.get_effective_permissions(FizzBuzzRole.FIZZ_READER)
        perm_strs = [f"{p.resource}:{p.range_spec}:{p.action}" for p in perms]
        assert "numbers:1:read" in perm_strs  # inherited
        assert "numbers:fizz:read" in perm_strs  # own
        assert "numbers:1-50:evaluate" in perm_strs  # own

    def test_buzz_admin_inherits_fizz_reader(self):
        perms = RoleRegistry.get_effective_permissions(FizzBuzzRole.BUZZ_ADMIN)
        perm_strs = [f"{p.resource}:{p.range_spec}:{p.action}" for p in perms]
        assert "numbers:1:read" in perm_strs  # from anonymous
        assert "numbers:fizz:read" in perm_strs  # from fizz_reader
        assert "numbers:buzz:read" in perm_strs  # own
        assert "numbers:1-100:evaluate" in perm_strs  # own

    def test_superuser_inherits_all(self):
        perms = RoleRegistry.get_effective_permissions(FizzBuzzRole.FIZZBUZZ_SUPERUSER)
        perm_strs = [f"{p.resource}:{p.range_spec}:{p.action}" for p in perms]
        assert "numbers:*:evaluate" in perm_strs
        assert "numbers:*:read" in perm_strs
        assert "numbers:*:configure" in perm_strs
        # Also inherited
        assert "numbers:1:read" in perm_strs

    def test_auditor_inherits_fizz_reader(self):
        perms = RoleRegistry.get_effective_permissions(FizzBuzzRole.NUMBER_AUDITOR)
        perm_strs = [f"{p.resource}:{p.range_spec}:{p.action}" for p in perms]
        assert "numbers:*:audit" in perm_strs
        assert "numbers:*:read" in perm_strs
        assert "numbers:1:read" in perm_strs  # from anonymous
        assert "numbers:fizz:read" in perm_strs  # from fizz_reader

    def test_suggested_upgrade_anonymous(self):
        assert RoleRegistry.get_suggested_upgrade_path(FizzBuzzRole.ANONYMOUS) == FizzBuzzRole.FIZZ_READER

    def test_suggested_upgrade_fizz_reader(self):
        assert RoleRegistry.get_suggested_upgrade_path(FizzBuzzRole.FIZZ_READER) == FizzBuzzRole.BUZZ_ADMIN

    def test_suggested_upgrade_buzz_admin(self):
        assert RoleRegistry.get_suggested_upgrade_path(FizzBuzzRole.BUZZ_ADMIN) == FizzBuzzRole.FIZZBUZZ_SUPERUSER

    def test_suggested_upgrade_superuser(self):
        assert RoleRegistry.get_suggested_upgrade_path(FizzBuzzRole.FIZZBUZZ_SUPERUSER) == FizzBuzzRole.FIZZBUZZ_SUPERUSER

    def test_permissions_are_deduplicated(self):
        """Ensure no duplicate permissions in effective permissions."""
        for role in FizzBuzzRole:
            perms = RoleRegistry.get_effective_permissions(role)
            perm_strs = [f"{p.resource}:{p.range_spec}:{p.action}" for p in perms]
            assert len(perm_strs) == len(set(perm_strs)), f"Duplicate permissions for {role}"


# ============================================================
# Token Engine Tests
# ============================================================


class TestFizzBuzzTokenEngine:
    def test_generate_token_format(self, secret):
        token = FizzBuzzTokenEngine.generate_token(
            user="testuser",
            role=FizzBuzzRole.FIZZ_READER,
            secret=secret,
        )
        parts = token.split(".")
        assert len(parts) == 3
        assert parts[0] == "EFP"

    def test_generate_and_validate_round_trip(self, secret):
        token = FizzBuzzTokenEngine.generate_token(
            user="testuser",
            role=FizzBuzzRole.BUZZ_ADMIN,
            secret=secret,
            ttl_seconds=3600,
        )
        auth = FizzBuzzTokenEngine.validate_token(token, secret)
        assert auth.user == "testuser"
        assert auth.role == FizzBuzzRole.BUZZ_ADMIN
        assert auth.token_id is not None
        assert auth.trust_mode is False

    def test_validate_populates_permissions(self, secret):
        token = FizzBuzzTokenEngine.generate_token(
            user="admin",
            role=FizzBuzzRole.FIZZBUZZ_SUPERUSER,
            secret=secret,
        )
        auth = FizzBuzzTokenEngine.validate_token(token, secret)
        assert len(auth.effective_permissions) > 0

    def test_expired_token_rejected(self, secret):
        token = FizzBuzzTokenEngine.generate_token(
            user="expired_user",
            role=FizzBuzzRole.FIZZ_READER,
            secret=secret,
            ttl_seconds=-1,  # Already expired
        )
        with pytest.raises(TokenValidationError, match="expired"):
            FizzBuzzTokenEngine.validate_token(token, secret)

    def test_tampered_token_rejected(self, secret):
        token = FizzBuzzTokenEngine.generate_token(
            user="honest_user",
            role=FizzBuzzRole.FIZZ_READER,
            secret=secret,
        )
        # Tamper with the payload
        parts = token.split(".")
        tampered = f"{parts[0]}.{parts[1]}x.{parts[2]}"
        with pytest.raises(TokenValidationError, match="signature"):
            FizzBuzzTokenEngine.validate_token(tampered, secret)

    def test_wrong_secret_rejected(self, secret):
        token = FizzBuzzTokenEngine.generate_token(
            user="user",
            role=FizzBuzzRole.FIZZ_READER,
            secret=secret,
        )
        with pytest.raises(TokenValidationError, match="signature"):
            FizzBuzzTokenEngine.validate_token(token, "wrong-secret")

    def test_invalid_format_rejected(self, secret):
        with pytest.raises(TokenValidationError, match="format"):
            FizzBuzzTokenEngine.validate_token("not.a.token", secret)

    def test_invalid_prefix_rejected(self, secret):
        with pytest.raises(TokenValidationError, match="format"):
            FizzBuzzTokenEngine.validate_token("JWT.payload.sig", secret)

    def test_token_with_all_roles(self, secret):
        """Ensure tokens work for all role types."""
        for role in FizzBuzzRole:
            token = FizzBuzzTokenEngine.generate_token(
                user=f"user_{role.name.lower()}",
                role=role,
                secret=secret,
            )
            auth = FizzBuzzTokenEngine.validate_token(token, secret)
            assert auth.role == role
            assert auth.user == f"user_{role.name.lower()}"

    def test_custom_issuer(self, secret):
        token = FizzBuzzTokenEngine.generate_token(
            user="user",
            role=FizzBuzzRole.ANONYMOUS,
            secret=secret,
            issuer="custom-issuer",
        )
        # Should still validate (issuer isn't checked during validation)
        auth = FizzBuzzTokenEngine.validate_token(token, secret)
        assert auth.user == "user"


# ============================================================
# _is_prime Tests
# ============================================================


class TestIsPrime:
    def test_primes(self):
        primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47]
        for p in primes:
            assert _is_prime(p) is True, f"{p} should be prime"

    def test_non_primes(self):
        non_primes = [0, 1, 4, 6, 8, 9, 10, 12, 14, 15, 16, 18, 20, 21, 25]
        for n in non_primes:
            assert _is_prime(n) is False, f"{n} should not be prime"

    def test_negative_numbers(self):
        assert _is_prime(-1) is False
        assert _is_prime(-7) is False

    def test_large_prime(self):
        assert _is_prime(97) is True
        assert _is_prime(101) is True

    def test_large_non_prime(self):
        assert _is_prime(100) is False
        assert _is_prime(99) is False


# ============================================================
# AccessDeniedResponseBuilder Tests
# ============================================================


class TestAccessDeniedResponseBuilder:
    def test_response_has_exactly_47_fields(self):
        """The 47-field count is sacred. This test enforces it."""
        body = AccessDeniedResponseBuilder.build(
            number=42,
            user="denied_user",
            role=FizzBuzzRole.ANONYMOUS,
            required_permission=Permission("numbers", "42", "evaluate"),
            granted_permissions=[Permission("numbers", "1", "read")],
        )
        assert len(body) == 47, (
            f"Access denied body has {len(body)} fields, but 47 are required."
        )

    def test_response_denied_flag(self):
        body = AccessDeniedResponseBuilder.build(
            number=15,
            user="user",
            role=FizzBuzzRole.FIZZ_READER,
            required_permission=Permission("numbers", "15", "evaluate"),
            granted_permissions=[],
        )
        assert body["denied"] is True

    def test_response_contains_user(self):
        body = AccessDeniedResponseBuilder.build(
            number=7,
            user="test_user",
            role=FizzBuzzRole.ANONYMOUS,
            required_permission=Permission("numbers", "7", "evaluate"),
            granted_permissions=[],
        )
        assert body["user"] == "test_user"

    def test_response_contains_number_analysis(self):
        body = AccessDeniedResponseBuilder.build(
            number=15,
            user="user",
            role=FizzBuzzRole.ANONYMOUS,
            required_permission=Permission("numbers", "15", "evaluate"),
            granted_permissions=[],
        )
        assert body["number_is_prime"] is False
        assert body["number_would_be_fizz"] is True
        assert body["number_would_be_buzz"] is True
        assert body["number_would_be_fizzbuzz"] is True

    def test_response_prime_number_detection(self):
        body = AccessDeniedResponseBuilder.build(
            number=7,
            user="user",
            role=FizzBuzzRole.ANONYMOUS,
            required_permission=Permission("numbers", "7", "evaluate"),
            granted_permissions=[],
        )
        assert body["number_is_prime"] is True

    def test_response_contains_incident_id(self):
        body = AccessDeniedResponseBuilder.build(
            number=1,
            user="user",
            role=FizzBuzzRole.ANONYMOUS,
            required_permission=Permission("numbers", "1", "evaluate"),
            granted_permissions=[],
        )
        assert body["incident_auto_filed"] is True
        assert body["incident_id"].startswith("INC-")

    def test_response_contains_suggested_upgrade(self):
        body = AccessDeniedResponseBuilder.build(
            number=1,
            user="user",
            role=FizzBuzzRole.ANONYMOUS,
            required_permission=Permission("numbers", "1", "evaluate"),
            granted_permissions=[],
        )
        assert body["suggested_role_upgrade_path"] == "FIZZ_READER"

    def test_response_custom_contact_email(self):
        body = AccessDeniedResponseBuilder.build(
            number=1,
            user="user",
            role=FizzBuzzRole.ANONYMOUS,
            required_permission=Permission("numbers", "1", "evaluate"),
            granted_permissions=[],
            contact_email="custom@example.com",
        )
        assert body["hr_contact_email"] == "custom@example.com"

    def test_response_contains_legal_disclaimer(self):
        body = AccessDeniedResponseBuilder.build(
            number=1,
            user="user",
            role=FizzBuzzRole.ANONYMOUS,
            required_permission=Permission("numbers", "1", "evaluate"),
            granted_permissions=[],
        )
        assert "as-is" in body["legal_disclaimer"].lower()


# ============================================================
# AuthorizationMiddleware Tests
# ============================================================


class TestAuthorizationMiddleware:
    def test_superuser_can_evaluate_any_number(self, superuser_context):
        middleware = AuthorizationMiddleware(auth_context=superuser_context)
        for number in [1, 3, 5, 15, 42, 100, 999]:
            context = ProcessingContext(number=number, session_id="test")
            result = middleware.process(context, lambda c: c)
            assert result.number == number

    def test_anonymous_cannot_evaluate_most_numbers(self, anonymous_context):
        middleware = AuthorizationMiddleware(auth_context=anonymous_context)
        # ANONYMOUS can only read number 1, but not evaluate anything
        context = ProcessingContext(number=5, session_id="test")
        with pytest.raises(InsufficientFizzPrivilegesError):
            middleware.process(context, lambda c: c)

    def test_fizz_reader_can_evaluate_within_range(self, fizz_reader_context):
        middleware = AuthorizationMiddleware(auth_context=fizz_reader_context)
        # FIZZ_READER can evaluate 1-50
        context = ProcessingContext(number=25, session_id="test")
        result = middleware.process(context, lambda c: c)
        assert result.number == 25

    def test_fizz_reader_cannot_evaluate_outside_range(self, fizz_reader_context):
        middleware = AuthorizationMiddleware(auth_context=fizz_reader_context)
        # FIZZ_READER cannot evaluate 51+
        context = ProcessingContext(number=51, session_id="test")
        with pytest.raises(InsufficientFizzPrivilegesError):
            middleware.process(context, lambda c: c)

    def test_buzz_admin_can_evaluate_1_to_100(self, buzz_admin_context):
        middleware = AuthorizationMiddleware(auth_context=buzz_admin_context)
        for number in [1, 50, 75, 100]:
            context = ProcessingContext(number=number, session_id="test")
            result = middleware.process(context, lambda c: c)
            assert result.number == number

    def test_buzz_admin_cannot_evaluate_over_100(self, buzz_admin_context):
        middleware = AuthorizationMiddleware(auth_context=buzz_admin_context)
        context = ProcessingContext(number=101, session_id="test")
        with pytest.raises(InsufficientFizzPrivilegesError):
            middleware.process(context, lambda c: c)

    def test_denial_contains_47_field_body(self, anonymous_context):
        middleware = AuthorizationMiddleware(auth_context=anonymous_context)
        context = ProcessingContext(number=42, session_id="test")
        with pytest.raises(InsufficientFizzPrivilegesError) as exc_info:
            middleware.process(context, lambda c: c)
        assert len(exc_info.value.denial_body) == 47

    def test_middleware_sets_metadata_on_success(self, superuser_context):
        middleware = AuthorizationMiddleware(auth_context=superuser_context)
        context = ProcessingContext(number=1, session_id="test")
        result = middleware.process(context, lambda c: c)
        assert result.metadata["auth_user"] == "superuser"
        assert result.metadata["auth_role"] == "FIZZBUZZ_SUPERUSER"

    def test_middleware_get_name(self, superuser_context):
        middleware = AuthorizationMiddleware(auth_context=superuser_context)
        assert middleware.get_name() == "AuthorizationMiddleware"

    def test_middleware_get_priority(self, superuser_context):
        middleware = AuthorizationMiddleware(auth_context=superuser_context)
        assert middleware.get_priority() == -10

    def test_event_published_on_grant(self, superuser_context):
        event_bus = MagicMock()
        middleware = AuthorizationMiddleware(
            auth_context=superuser_context, event_bus=event_bus
        )
        context = ProcessingContext(number=1, session_id="test")
        middleware.process(context, lambda c: c)

        granted_calls = [
            call for call in event_bus.publish.call_args_list
            if call[0][0].event_type == EventType.AUTHORIZATION_GRANTED
        ]
        assert len(granted_calls) == 1

    def test_event_published_on_denial(self, anonymous_context):
        event_bus = MagicMock()
        middleware = AuthorizationMiddleware(
            auth_context=anonymous_context, event_bus=event_bus
        )
        context = ProcessingContext(number=42, session_id="test")
        with pytest.raises(InsufficientFizzPrivilegesError):
            middleware.process(context, lambda c: c)

        denied_calls = [
            call for call in event_bus.publish.call_args_list
            if call[0][0].event_type == EventType.AUTHORIZATION_DENIED
        ]
        assert len(denied_calls) == 1

    def test_auditor_cannot_evaluate(self, auditor_context):
        """NUMBER_AUDITOR has audit and read, but not evaluate for all numbers."""
        middleware = AuthorizationMiddleware(auth_context=auditor_context)
        # Auditor inherits FIZZ_READER's evaluate for 1-50
        context = ProcessingContext(number=25, session_id="test")
        result = middleware.process(context, lambda c: c)
        assert result.number == 25

        # But cannot evaluate beyond 50
        context = ProcessingContext(number=51, session_id="test")
        with pytest.raises(InsufficientFizzPrivilegesError):
            middleware.process(context, lambda c: c)


# ============================================================
# Exception Tests
# ============================================================


class TestAuthExceptions:
    def test_authentication_error(self):
        err = AuthenticationError("test")
        assert "EFP-A000" in str(err)

    def test_insufficient_privileges_error(self):
        body = {"field1": "value1"}
        err = InsufficientFizzPrivilegesError("denied", denial_body=body)
        assert "EFP-A001" in str(err)
        assert err.denial_body == body

    def test_number_classification_error(self):
        err = NumberClassificationLevelExceededError(42, "LOW", "TOP_SECRET")
        assert "EFP-A002" in str(err)
        assert "42" in str(err)

    def test_token_validation_error(self):
        err = TokenValidationError("bad token")
        assert "EFP-A003" in str(err)
        assert "bad token" in str(err)

    def test_token_validation_error_inherits_authentication(self):
        err = TokenValidationError("test")
        assert isinstance(err, AuthenticationError)


# ============================================================
# EventType Tests
# ============================================================


class TestAuthEventTypes:
    def test_new_event_types_exist(self):
        assert EventType.AUTHORIZATION_GRANTED is not None
        assert EventType.AUTHORIZATION_DENIED is not None
        assert EventType.TOKEN_VALIDATED is not None
        assert EventType.TOKEN_VALIDATION_FAILED is not None


# ============================================================
# FizzBuzzRole Tests
# ============================================================


class TestFizzBuzzRole:
    def test_all_roles_exist(self):
        assert FizzBuzzRole.ANONYMOUS is not None
        assert FizzBuzzRole.FIZZ_READER is not None
        assert FizzBuzzRole.BUZZ_ADMIN is not None
        assert FizzBuzzRole.FIZZBUZZ_SUPERUSER is not None
        assert FizzBuzzRole.NUMBER_AUDITOR is not None

    def test_roles_are_unique(self):
        values = [r.value for r in FizzBuzzRole]
        assert len(values) == len(set(values))


# ============================================================
# Config Tests
# ============================================================


class TestRBACConfig:
    def test_config_defaults(self):
        config = ConfigurationManager()
        config.load()
        assert config.rbac_enabled is False
        assert config.rbac_default_role == "ANONYMOUS"
        assert config.rbac_token_secret == "enterprise-fizzbuzz-secret-do-not-share"
        assert config.rbac_token_ttl_seconds == 3600
        assert config.rbac_token_issuer == "enterprise-fizzbuzz-platform"
        assert "fizzbuzz-security" in config.rbac_access_denied_contact_email
        assert config.rbac_next_training_session == "2026-04-01T09:00:00Z"


# ============================================================
# Model Tests
# ============================================================


class TestAuthModels:
    def test_permission_is_frozen(self):
        perm = Permission(resource="numbers", range_spec="*", action="evaluate")
        with pytest.raises(AttributeError):
            perm.resource = "other"

    def test_auth_context_is_frozen(self):
        ctx = AuthContext(user="test", role=FizzBuzzRole.ANONYMOUS)
        with pytest.raises(AttributeError):
            ctx.user = "other"

    def test_auth_context_defaults(self):
        ctx = AuthContext(user="test", role=FizzBuzzRole.ANONYMOUS)
        assert ctx.token_id is None
        assert ctx.effective_permissions == ()
        assert ctx.trust_mode is False


# ============================================================
# Integration Tests
# ============================================================


class TestAuthIntegration:
    def test_full_pipeline_with_superuser(self, superuser_context):
        """Test authorization middleware in a full middleware pipeline."""
        from middleware import MiddlewarePipeline, ValidationMiddleware

        auth_mw = AuthorizationMiddleware(auth_context=superuser_context)
        validation_mw = ValidationMiddleware()

        pipeline = MiddlewarePipeline()
        pipeline.add(auth_mw)
        pipeline.add(validation_mw)

        context = ProcessingContext(number=42, session_id="test")
        result = pipeline.execute(context, lambda c: c)
        assert result.number == 42
        assert result.metadata["auth_user"] == "superuser"

    def test_full_pipeline_with_denial(self, anonymous_context):
        """Test that authorization middleware blocks before other middleware runs."""
        from middleware import MiddlewarePipeline, TimingMiddleware

        auth_mw = AuthorizationMiddleware(auth_context=anonymous_context)
        timing_mw = TimingMiddleware()

        pipeline = MiddlewarePipeline()
        pipeline.add(auth_mw)
        pipeline.add(timing_mw)

        context = ProcessingContext(number=42, session_id="test")
        with pytest.raises(InsufficientFizzPrivilegesError):
            pipeline.execute(context, lambda c: c)

    def test_token_to_middleware_integration(self, secret):
        """Test the full flow: generate token -> validate -> create middleware -> evaluate."""
        token = FizzBuzzTokenEngine.generate_token(
            user="integration_user",
            role=FizzBuzzRole.FIZZBUZZ_SUPERUSER,
            secret=secret,
        )
        auth_context = FizzBuzzTokenEngine.validate_token(token, secret)
        middleware = AuthorizationMiddleware(auth_context=auth_context)

        context = ProcessingContext(number=42, session_id="test")
        result = middleware.process(context, lambda c: c)
        assert result.metadata["auth_user"] == "integration_user"

    def test_service_builder_with_auth_context(self, superuser_context):
        """Test that the service builder accepts auth context."""
        from fizzbuzz_service import FizzBuzzServiceBuilder

        config = ConfigurationManager()
        config.load()
        builder = FizzBuzzServiceBuilder().with_config(config).with_auth_context(superuser_context)
        # Just verify it doesn't crash — auth context is stored
        assert builder._auth_context is superuser_context
