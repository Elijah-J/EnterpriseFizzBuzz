"""Rbac configuration properties."""

from __future__ import annotations

from typing import Any


class RbacConfigMixin:
    """Configuration properties for the rbac subsystem."""

    @property
    def rbac_enabled(self) -> bool:
        """Whether Role-Based Access Control is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("rbac", {}).get("enabled", False)

    @property
    def rbac_default_role(self) -> str:
        """The default role for unauthenticated users."""
        self._ensure_loaded()
        return self._raw_config.get("rbac", {}).get("default_role", "ANONYMOUS")

    @property
    def rbac_token_secret(self) -> str:
        """The HMAC secret for token signing and validation."""
        self._ensure_loaded()
        return self._raw_config.get("rbac", {}).get(
            "token_secret", "enterprise-fizzbuzz-secret-do-not-share"
        )

    @property
    def rbac_token_ttl_seconds(self) -> int:
        """Token time-to-live in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("rbac", {}).get("token_ttl_seconds", 3600)

    @property
    def rbac_token_issuer(self) -> str:
        """Token issuer identifier."""
        self._ensure_loaded()
        return self._raw_config.get("rbac", {}).get(
            "token_issuer", "enterprise-fizzbuzz-platform"
        )

    @property
    def rbac_access_denied_contact_email(self) -> str:
        """Contact email for access denied responses."""
        self._ensure_loaded()
        return self._raw_config.get("rbac", {}).get(
            "access_denied_contact_email", "fizzbuzz-security@enterprise.example.com"
        )

    @property
    def rbac_next_training_session(self) -> str:
        """Next available RBAC training session datetime."""
        self._ensure_loaded()
        return self._raw_config.get("rbac", {}).get(
            "next_training_session", "2026-04-01T09:00:00Z"
        )

