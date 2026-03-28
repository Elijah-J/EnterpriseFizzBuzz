"""
Enterprise FizzBuzz Platform - FizzSecretsV2: Enhanced Secrets Management

Rotation, dynamic secrets, lease management, versioning.

Architecture reference: HashiCorp Vault, AWS Secrets Manager, CyberArk.
"""

from __future__ import annotations

import hashlib
import logging
import random
import string
import time
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzsecretsv2 import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzsecretsv2")
EVENT_SECRET_ROTATED = EventType.register("FIZZSECRETSV2_ROTATED")

FIZZSECRETSV2_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 182

class SecretType(Enum):
    STATIC = "static"
    DYNAMIC = "dynamic"
    ROTATING = "rotating"

class LeaseState(Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"

@dataclass
class FizzSecretsV2Config:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class Secret:
    secret_id: str = ""
    name: str = ""
    value: str = ""
    secret_type: SecretType = SecretType.STATIC
    version: int = 1
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Lease:
    lease_id: str = ""
    secret_name: str = ""
    granted_to: str = ""
    state: LeaseState = LeaseState.ACTIVE
    granted_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    ttl_seconds: float = 3600.0


class SecretStore:
    def __init__(self) -> None:
        self._secrets: Dict[str, Secret] = OrderedDict()
        self._versions: Dict[str, Dict[int, Secret]] = defaultdict(dict)

    def put(self, name: str, value: str, secret_type: SecretType = SecretType.STATIC,
            metadata: Optional[Dict[str, Any]] = None) -> Secret:
        now = datetime.now(timezone.utc)
        existing = self._secrets.get(name)
        version = (existing.version + 1) if existing else 1
        secret = Secret(secret_id=f"sec-{uuid.uuid4().hex[:8]}", name=name, value=value,
                        secret_type=secret_type, version=version, created_at=now,
                        metadata=metadata or {})
        self._secrets[name] = secret
        self._versions[name][version] = secret
        return secret

    def get(self, name: str) -> Secret:
        secret = self._secrets.get(name)
        if secret is None:
            raise FizzSecretsV2NotFoundError(name)
        return secret

    def delete(self, name: str) -> bool:
        return self._secrets.pop(name, None) is not None

    def list_secrets(self) -> List[Secret]:
        return list(self._secrets.values())

    def rotate(self, name: str) -> Secret:
        existing = self.get(name)
        # Generate new value
        new_value = hashlib.sha256(f"{existing.value}:{time.time()}:{uuid.uuid4().hex}".encode()).hexdigest()[:32]
        return self.put(name, new_value, existing.secret_type, existing.metadata)

    def get_version(self, name: str, version: int) -> Secret:
        versions = self._versions.get(name, {})
        secret = versions.get(version)
        if secret is None:
            raise FizzSecretsV2NotFoundError(f"{name} v{version}")
        return secret


class LeaseManager:
    def __init__(self) -> None:
        self._leases: OrderedDict[str, Lease] = OrderedDict()

    def grant(self, secret_name: str, granted_to: str, ttl: float = 3600.0) -> Lease:
        now = datetime.now(timezone.utc)
        lease = Lease(lease_id=f"lease-{uuid.uuid4().hex[:8]}", secret_name=secret_name,
                      granted_to=granted_to, state=LeaseState.ACTIVE, granted_at=now,
                      expires_at=now + timedelta(seconds=ttl), ttl_seconds=ttl)
        self._leases[lease.lease_id] = lease
        return lease

    def revoke(self, lease_id: str) -> None:
        lease = self._leases.get(lease_id)
        if lease:
            lease.state = LeaseState.REVOKED

    def get_lease(self, lease_id: str) -> Optional[Lease]:
        return self._leases.get(lease_id)

    def list_active_leases(self) -> List[Lease]:
        return [l for l in self._leases.values() if l.state == LeaseState.ACTIVE]

    def expire_leases(self) -> int:
        now = datetime.now(timezone.utc)
        count = 0
        for lease in self._leases.values():
            if lease.state == LeaseState.ACTIVE and lease.expires_at and lease.expires_at <= now:
                lease.state = LeaseState.EXPIRED
                count += 1
        return count


class DynamicSecretGenerator:
    def generate(self, template: str = "password", context: Optional[Dict[str, Any]] = None) -> str:
        ctx = context or {}
        if template == "password":
            length = ctx.get("length", 24)
            chars = string.ascii_letters + string.digits + "!@#$%^&*"
            return "".join(random.choice(chars) for _ in range(length))
        elif template == "token":
            prefix = ctx.get("prefix", "tok")
            return f"{prefix}_{uuid.uuid4().hex}"
        elif template == "key":
            return hashlib.sha256(uuid.uuid4().hex.encode()).hexdigest()
        else:
            return uuid.uuid4().hex


class FizzSecretsV2Dashboard:
    def __init__(self, store: Optional[SecretStore] = None, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._store = store; self._width = width
    def render(self) -> str:
        lines = ["=" * self._width, "FizzSecretsV2 Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZSECRETSV2_VERSION}"]
        if self._store:
            secrets = self._store.list_secrets()
            lines.append(f"  Secrets: {len(secrets)}")
            for s in secrets:
                lines.append(f"  {s.name:<25} v{s.version} {s.secret_type.value}")
        return "\n".join(lines)


class FizzSecretsV2Middleware(IMiddleware):
    def __init__(self, store: Optional[SecretStore] = None, dashboard: Optional[FizzSecretsV2Dashboard] = None) -> None:
        self._store = store; self._dashboard = dashboard
    def get_name(self) -> str: return "fizzsecretsv2"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY
    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler: return next_handler(ctx)
        return ctx
    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzsecretsv2_subsystem(dashboard_width: int = DEFAULT_DASHBOARD_WIDTH) -> Tuple[SecretStore, FizzSecretsV2Dashboard, FizzSecretsV2Middleware]:
    store = SecretStore()
    store.put("database/password", "fizzbuzz-db-secret-2026", SecretType.ROTATING)
    store.put("api/token", "tok_fizzbuzz_production", SecretType.STATIC)
    store.put("tls/certificate", "-----BEGIN CERTIFICATE-----\nFizzBuzz\n-----END CERTIFICATE-----", SecretType.STATIC)
    dashboard = FizzSecretsV2Dashboard(store, dashboard_width)
    middleware = FizzSecretsV2Middleware(store, dashboard)
    logger.info("FizzSecretsV2 initialized: %d secrets", len(store.list_secrets()))
    return store, dashboard, middleware
